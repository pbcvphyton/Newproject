"""
JurisIntel — Sincronização com Google Drive e Google Sheets.

Funcionalidades:
  1. Upload automático de PDFs organizados por área/ano
  2. Sync de planilhas Excel para pasta compartilhada
  3. Backup do banco SQLite
  4. Atualização do Google Sheets colaborativo (4 abas)

Setup:
  1. Acesse https://console.cloud.google.com/
  2. Crie projeto → habilite Drive API + Sheets API
  3. Crie credenciais OAuth 2.0 (tipo Desktop)
  4. Salve o JSON em config/credentials.json
  5. Na primeira execução, o navegador abrirá para autorização

Bugs corrigidos vs versão original:
  - str.padStart() (JavaScript) → str.zfill() (Python)
  - Newline embutida em string de cabeçalho corrigida
  - Bloco area_map completado (estava truncado)
"""

import os
import json
import logging
import mimetypes
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    logger.info("Google API não instalada. Execute: pip install google-api-python-client "
                "google-auth-httplib2 google-auth-oauthlib")

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
]

DRIVE_STRUCTURE = {
    'root': 'JurisIntel — TJ-SP',
    'subfolders': {
        'pdfs':      '📄 PDFs Acórdãos',
        'exports':   '📊 Exportações Excel',
        'backups':   '💾 Backups',
        'relatorios':'📋 Relatórios IA',
    },
}


class GoogleDriveSync:
    """Sincroniza dados do sistema com o Google Drive."""

    def __init__(self, credentials_path='config/credentials.json',
                 token_path='config/token.json'):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API não instalada.\n"
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        self.credentials_path = credentials_path
        self.token_path       = token_path
        self.service          = None
        self.folder_ids       = {}
        self._authenticate()
        self._ensure_folder_structure()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Credenciais não encontradas: {self.credentials_path}\n"
                        "Baixe em https://console.cloud.google.com/"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, 'w') as f:
                f.write(creds.to_json())
        self.service = build('drive', 'v3', credentials=creds)
        logger.info("Autenticado no Google Drive.")

    def _find_folder(self, name, parent_id=None):
        q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
             f"and trashed=false")
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = self.service.files().list(q=q, spaces='drive',
                                        fields='files(id,name)').execute()
        files = res.get('files', [])
        return files[0]['id'] if files else None

    def _create_folder(self, name, parent_id=None):
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            meta['parents'] = [parent_id]
        f = self.service.files().create(body=meta, fields='id').execute()
        logger.info(f"Pasta criada: {name}")
        return f['id']

    def _ensure_folder_structure(self):
        root_name = DRIVE_STRUCTURE['root']
        root_id = self._find_folder(root_name) or self._create_folder(root_name)
        self.folder_ids['root'] = root_id
        for key, name in DRIVE_STRUCTURE['subfolders'].items():
            fid = self._find_folder(name, root_id) or self._create_folder(name, root_id)
            self.folder_ids[key] = fid

    def upload_file(self, local_path, drive_folder_key='root',
                    subfolder=None, description=None) -> dict:
        """Faz upload de um arquivo, atualizando se já existir."""
        parent_id = self.folder_ids.get(drive_folder_key, self.folder_ids['root'])
        if subfolder:
            sub_id = self._find_folder(subfolder, parent_id) or \
                     self._create_folder(subfolder, parent_id)
            parent_id = sub_id

        filename  = os.path.basename(local_path)
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'

        existing = self.service.files().list(
            q=f"name='{filename}' and '{parent_id}' in parents and trashed=false",
            fields='files(id)'
        ).execute().get('files', [])

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        if existing:
            f = self.service.files().update(
                fileId=existing[0]['id'], media_body=media,
                fields='id,webViewLink').execute()
        else:
            meta = {'name': filename, 'parents': [parent_id]}
            if description:
                meta['description'] = description
            f = self.service.files().create(
                body=meta, media_body=media, fields='id,webViewLink').execute()

        logger.info(f"Upload: {filename}")
        return {'id': f['id'], 'url': f.get('webViewLink', '')}

    def upload_pdf_nomenclatura(self, local_path, numero_sequencial, tipo_acao,
                                uf, numero_processo, area_direito=None, ano=None):
        """
        Upload com nomenclatura padronizada:
        0001_Negativa_Cobertura_SP_2189012-34.2025.8.26.0100.pdf
        """
        tipo_limpo = ''.join(
            c if c.isalnum() or c == '_' else '_'
            for c in tipo_acao.replace(' ', '_')
        ).strip('_')
        # CORREÇÃO: .zfill() em Python (não .padStart() do JavaScript)
        nome = f"{str(numero_sequencial).zfill(4)}_{tipo_limpo}_{uf}_{numero_processo}.pdf"

        tmp = os.path.join('/tmp', nome)
        shutil.copy2(local_path, tmp)
        try:
            subfolder = area_direito or 'Geral'
            if ano:
                subfolder = f"{subfolder}/{ano}"
            result = self.upload_file(tmp, drive_folder_key='pdfs',
                                      subfolder=subfolder,
                                      description=f"{tipo_acao} | {numero_processo}")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return result

    def upload_export(self, local_path, description=None):
        return self.upload_file(local_path, drive_folder_key='exports',
                                description=description)

    def backup_database(self, db_path='data/jurisprudencia.db'):
        if not os.path.exists(db_path):
            logger.warning(f"Banco não encontrado: {db_path}")
            return None
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        tmp = f'/tmp/jurisprudencia_backup_{ts}.db'
        shutil.copy2(db_path, tmp)
        try:
            result = self.upload_file(tmp, drive_folder_key='backups',
                                      description=f"Backup — {datetime.now():%d/%m/%Y %H:%M}")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        logger.info("Backup enviado ao Drive.")
        return result

    def sync_all_pdfs(self, pdf_dir='data/pdfs') -> dict:
        if not os.path.exists(pdf_dir):
            return {'total': 0, 'enviados': 0, 'erros': 0}
        pdfs = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
        stats = {'total': len(pdfs), 'enviados': 0, 'erros': 0}
        for pdf_file in pdfs:
            try:
                self.upload_pdf_nomenclatura(
                    os.path.join(pdf_dir, pdf_file), 0, 'Acordao', 'SP', pdf_file
                )
                stats['enviados'] += 1
            except Exception as exc:
                logger.error(f"Erro ao enviar {pdf_file}: {exc}")
                stats['erros'] += 1
        return stats


class GoogleSheetsSync:
    """Atualiza planilha Google Sheets com dados do banco (4 abas)."""

    def __init__(self, credentials_path='config/credentials.json',
                 token_path='config/token.json'):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError("Google API não instalada.")
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        return build('sheets', 'v4', credentials=creds)

    def create_or_update_sheet(self, spreadsheet_id=None,
                               title='JurisIntel — Dados TJ-SP',
                               decisoes=None, drive_folder_url=None) -> dict:
        if not decisoes:
            return {}

        # ── Aba 1: Todas as Decisões ──────────────────────────────────────────
        headers_all = [
            'Seq', 'Nome do Arquivo', 'Link PDF', 'Nº Processo', 'UF',
            'Classe', 'Área do Direito', 'Tipo de Ação',
            'Tese Principal', 'Tese Secundária', 'Resultado', 'Resultado Detalhado',
            'Autor (Tipo)', 'Autor', 'Réu (Tipo)', 'Réu',
            'Comarca', 'Relator', 'Órgão Julgador',
            'Data Julgamento', 'Data Publicação',
            'Valor Causa', 'Valor Condenação', 'Dano Moral',
            'Fundamentação', 'Precedentes', 'Palavras-chave',
            'Resumo IA', 'Ementa',
        ]
        campos = [
            'numero_processo', 'numero_processo', 'drive_url', 'numero_processo', '',
            'classe_processual', 'area_direito', 'tipo_acao',
            'tese_principal', 'tese_secundaria', 'resultado', 'resultado_detalhado',
            'autor_tipo', 'autor_nome', 'reu_tipo', 'reu_nome',
            'comarca', 'relator', 'orgao_julgador',
            'data_julgamento', 'data_publicacao',
            'valor_causa', 'valor_condenacao', 'dano_moral_valor',
            'fundamentacao_legal', 'precedentes_citados', 'palavras_chave',
            'resumo_ia', 'ementa',
        ]
        rows_all = [headers_all]
        for i, d in enumerate(decisoes, 1):
            proc      = d.get('numero_processo', '')
            tipo      = d.get('tipo_acao', 'Geral')
            tipo_limpo = ''.join(c if c.isalnum() or c == '_' else '_'
                                 for c in tipo.replace(' ', '_'))
            # CORREÇÃO: .zfill() (Python) no lugar de .padStart() (JavaScript)
            nome_arq  = f"{str(i).zfill(4)}_{tipo_limpo}_SP_{proc}.pdf"
            row = [str(i), nome_arq, d.get('drive_url', ''), proc, 'SP']
            for campo in campos[5:]:
                val = d.get(campo, '')
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(str(val) if val else '')
            rows_all.append(row)

        # ── Aba 2: Por Tese ───────────────────────────────────────────────────
        tese_map: dict = {}
        for d in decisoes:
            tese = d.get('tese_principal') or 'Não classificado'
            if tese not in tese_map:
                tese_map[tese] = {'pos': 0, 'neg': 0, 'total': 0,
                                  'areas': set(), 'valores': []}
            tese_map[tese]['total'] += 1
            res = (d.get('resultado') or '').lower()
            if 'provido' in res and 'não' not in res:
                tese_map[tese]['pos'] += 1
            else:
                tese_map[tese]['neg'] += 1
            if d.get('area_direito'):
                tese_map[tese]['areas'].add(d['area_direito'])
            try:
                if d.get('valor_causa'):
                    tese_map[tese]['valores'].append(float(d['valor_causa']))
            except (ValueError, TypeError):
                pass

        rows_tese = [['Tese', 'Total', 'Favoráveis', 'Desfavoráveis',
                      'Taxa Êxito (%)', 'Áreas', 'Valor Médio']]
        for tese, s in sorted(tese_map.items(), key=lambda x: -x[1]['total']):
            taxa = (s['pos'] / s['total'] * 100) if s['total'] else 0
            vlr  = sum(s['valores']) / len(s['valores']) if s['valores'] else 0
            rows_tese.append([
                tese, s['total'], s['pos'], s['neg'],
                f"{taxa:.1f}%", ', '.join(s['areas']),
                f"R$ {vlr:,.0f}" if vlr else '—',
            ])

        # ── Aba 3: Por Área ───────────────────────────────────────────────────
        area_map: dict = {}
        for d in decisoes:
            area = d.get('area_direito') or 'Não classificado'
            if area not in area_map:
                area_map[area] = {'pos': 0, 'neg': 0, 'total': 0}
            area_map[area]['total'] += 1
            res = (d.get('resultado') or '').lower()
            if 'provido' in res and 'não' not in res:
                area_map[area]['pos'] += 1
            else:
                area_map[area]['neg'] += 1

        rows_area = [['Área do Direito', 'Total', 'Favoráveis',
                      'Desfavoráveis', 'Taxa Êxito (%)']]
        for area, s in sorted(area_map.items(), key=lambda x: -x[1]['total']):
            taxa = (s['pos'] / s['total'] * 100) if s['total'] else 0
            rows_area.append([area, s['total'], s['pos'], s['neg'], f"{taxa:.1f}%"])

        # ── Aba 4: Dashboard ──────────────────────────────────────────────────
        total     = len(decisoes)
        total_pos = sum(1 for d in decisoes
                        if 'provido' in (d.get('resultado') or '').lower()
                        and 'não' not in (d.get('resultado') or '').lower())
        rows_dash = [
            ['JurisIntel — Dashboard TJ-SP'],
            [f'Atualizado: {datetime.now():%d/%m/%Y %H:%M}'],
            [''],
            ['Métrica', 'Valor'],
            ['Total de decisões',   total],
            ['Favoráveis',          total_pos],
            ['Desfavoráveis',       total - total_pos],
            ['Taxa geral de êxito', f"{(total_pos/total*100):.1f}%" if total else '0%'],
            ['Teses mapeadas',      len(tese_map)],
            ['Áreas do direito',    len(area_map)],
            [''],
            ['PDFs no Drive', drive_folder_url or 'Configurar em config.yaml'],
        ]

        # ── Escrever ou criar planilha ────────────────────────────────────────
        abas = [
            ('Todas as Decisões', rows_all),
            ('Por Tese',          rows_tese),
            ('Por Área',          rows_area),
            ('Dashboard',         rows_dash),
        ]
        if spreadsheet_id:
            for aba_nome, rows in abas:
                try:
                    self.service.spreadsheets().values().clear(
                        spreadsheetId=spreadsheet_id,
                        range=f'{aba_nome}!A:AZ'
                    ).execute()
                    self.service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f'{aba_nome}!A1',
                        valueInputOption='RAW',
                        body={'values': rows}
                    ).execute()
                except Exception as exc:
                    logger.warning(f"Erro ao atualizar aba {aba_nome}: {exc}")
            url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        else:
            ss = self.service.spreadsheets().create(body={
                'properties': {'title': title},
                'sheets': [{'properties': {'title': n}} for n, _ in abas],
            }).execute()
            sid = ss['spreadsheetId']
            for aba_nome, rows in abas:
                self.service.spreadsheets().values().update(
                    spreadsheetId=sid, range=f'{aba_nome}!A1',
                    valueInputOption='RAW', body={'values': rows}
                ).execute()
            spreadsheet_id = sid
            url = f"https://docs.google.com/spreadsheets/d/{sid}"

        logger.info(f"Google Sheets: {url}")
        return {'spreadsheetId': spreadsheet_id, 'url': url}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if not GOOGLE_API_AVAILABLE:
        print("Google API não disponível.\n"
              "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    else:
        print("Google API disponível. Configure config/credentials.json para começar.")
