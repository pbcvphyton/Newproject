"""
JurisIntel — Scraper da Consulta de Jurisprudência do 2º Grau (CJSG/ESAJ TJ-SP).

Estratégia de parsing multi-camada:
  1. Tenta extração via seletores CSS do layout atual do ESAJ
  2. Fallback para regex no texto completo da página
  3. Fallback final para parsing genérico de padrões numéricos

Boas práticas embutidas:
  - Delay aleatório entre requisições (2–5 s por padrão)
  - Retry automático com backoff exponencial (via tenacity)
  - User-Agent identificado
  - Sessão aquecida antes da primeira busca
"""

import re
import time
import random
import logging
import argparse
import os
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import JurisprudenciaDB

logger = logging.getLogger(__name__)

BASE_URL   = "https://esaj.tjsp.jus.br"
CJSG_URL   = f"{BASE_URL}/cjsg/resultadoCompleta.do"
ACORDAO_URL = f"{BASE_URL}/cjsg/getArquivo.do"
INIT_URL   = f"{BASE_URL}/cjsg/consultaCompleta.do"

# Regex do número de processo (CNJ)
RE_PROCESSO = re.compile(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}')


class CJSGScraper:
    """Coleta metadados e URLs de acórdãos no ESAJ/CJSG TJ-SP."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':      self.config.get('user_agent',
                'Mozilla/5.0 (compatible) JurisprudenciaBot/2.0 '
                '(pesquisa-juridica; contato: bot@jurisintel.com.br)'),
            'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection':      'keep-alive',
            'Referer':         INIT_URL,
        })
        self.delay_min   = self.config.get('delay_min_segundos', 2)
        self.delay_max   = self.config.get('delay_max_segundos', 5)
        self.max_retries = self.config.get('max_retries', 3)
        self.timeout     = self.config.get('timeout_segundos', 30)
        self.db          = JurisprudenciaDB(self.config.get('db_path', 'data/jurisprudencia.db'))
        self._sessao_inicializada = False

    # ─── Helpers de baixo nível ──────────────────────────────────────────────

    def _delay(self):
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _get(self, url, params=None) -> requests.Response:
        self._delay()
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        return resp

    def _inicializar_sessao(self):
        """Aquece a sessão visitando a página de consulta para obter cookies."""
        if self._sessao_inicializada:
            return
        logger.info("Inicializando sessão no ESAJ…")
        try:
            self._get(INIT_URL)
            self._sessao_inicializada = True
            logger.info("Sessão inicializada.")
        except Exception as e:
            logger.warning(f"Falha ao inicializar sessão: {e}. Continuando mesmo assim.")

    # ─── Busca ───────────────────────────────────────────────────────────────

    def buscar(self, termo_busca: str, pagina: int = 1, classe: str = None,
               data_inicio: str = None, data_fim: str = None,
               tipo_decisao: str = 'A') -> str:
        """Executa uma consulta no CJSG e retorna o HTML bruto."""
        params = {
            'conversationId':               '',
            'dados.buscaInteiroTeor':        termo_busca,
            'dados.pesquisarComSinonimos':   'S',
            'dados.buscaEmenta':             '',
            'dados.nuProcOrigem':            '',
            'dados.nuRegistro':              '',
            'dados.dtJulgamentoInicio':      data_inicio or '',
            'dados.dtJulgamentoFim':         data_fim    or '',
            'dados.dtPublicacaoInicio':      '',
            'dados.dtPublicacaoFim':         '',
            'dados.orpiComarcaOrig':         '',
            'tipoDecisao':                   tipo_decisao,
            'dados.ordenarPor':              'dtPublicacao',
        }
        if pagina > 1:
            params['paginaConsulta'] = str(pagina)
        if classe:
            params['dados.classe'] = classe
        return self._get(CJSG_URL, params=params).text

    # ─── Extração de dados ────────────────────────────────────────────────────

    def _total_paginas(self, html: str) -> int:
        soup = BeautifulSoup(html, 'lxml')

        # Estratégia 1 — elemento com id de total de resultados
        for sel in ('#totalResultadosBusca', '#totalResultadosBusca-fluxo'):
            elem = soup.select_one(sel)
            if elem:
                txt = elem.get_text(strip=True).replace('.', '')
                m = re.search(r'(\d+)', txt)
                if m:
                    return max(1, (int(m.group(1)) + 19) // 20)

        # Estratégia 2 — links de paginação
        nums = [int(a.get_text(strip=True))
                for a in soup.select('a.paginacao')
                if a.get_text(strip=True).isdigit()]
        if nums:
            return max(nums)

        # Estratégia 3 — se há resultado algum
        return 1 if soup.select('.fundocinza1, .resultadoLista tr, .ementa') else 0

    def _extrair_decisoes(self, html: str) -> list:
        soup = BeautifulSoup(html, 'lxml')
        decisoes = []

        # Estratégia 1 — linhas com classe fundocinza (layout clássico)
        rows = soup.select('tr.fundocinza1, tr.fundocinza2')

        # Estratégia 2 — qualquer tr dentro da tabela de resultados
        if not rows:
            rows = soup.select('table.resultadoLista tr')

        # Estratégia 3 — divs de ementa (layout moderno)
        if not rows:
            for div in soup.select('div.mensagemSemFormatacao'):
                parent = div.find_parent('tr') or div.find_parent('div', class_=re.compile(r'resultado'))
                if parent:
                    rows.append(parent)

        for row in rows:
            try:
                d = self._extrair_de_elemento(row)
                if d and d.get('numero_processo'):
                    decisoes.append(d)
            except Exception as exc:
                logger.debug(f"Falha ao extrair linha: {exc}")

        return decisoes

    def _extrair_de_elemento(self, elem) -> dict | None:
        dados = {}
        texto = elem.get_text(separator='\n', strip=True)

        # ── Número do processo e URL do acórdão ──
        for a in elem.find_all('a', href=True):
            href = a['href']
            link_txt = a.get_text(strip=True)

            if 'cdAcordao' in href or 'getArquivo' in href:
                m = re.search(r'cdAcordao=(\d+)', href)
                if m:
                    dados['codigo_decisao'] = m.group(1)
                    dados['url_acordao'] = f"{ACORDAO_URL}?cdAcordao={m.group(1)}&cdForo=0"

            m = RE_PROCESSO.search(link_txt)
            if m:
                dados['numero_processo'] = m.group(0)

        if 'numero_processo' not in dados:
            m = RE_PROCESSO.search(texto)
            if m:
                dados['numero_processo'] = m.group(0)

        if not dados.get('numero_processo'):
            return None

        # ── Campos via regex ──
        patterns = {
            'classe_processual': r'Classe[/\s]*Assunto:\s*(.+?)(?:\n|Relator)',
            'relator':           r'Relator\(a\)?:\s*(.+?)(?:\n|Comarca)',
            'comarca':           r'Comarca:\s*(.+?)(?:\n|Órgão)',
            'orgao_julgador':    r'Órgão [Jj]ulgador:\s*(.+?)(?:\n|Data)',
            'data_julgamento':   r'Data do [Jj]ulgamento:\s*(\d{2}/\d{2}/\d{4})',
            'data_publicacao':   r'Data de [Pp]ublicação:\s*(\d{2}/\d{2}/\d{4})',
            'data_registro':     r'Data de [Rr]egistro:\s*(\d{2}/\d{2}/\d{4})',
        }
        for campo, pat in patterns.items():
            m = re.search(pat, texto)
            if m:
                val = m.group(1).strip()
                if campo.startswith('data_'):
                    try:
                        val = datetime.strptime(val, '%d/%m/%Y').strftime('%Y-%m-%d')
                    except ValueError:
                        pass
                dados[campo] = val

        # ── Separar classe e assunto ──
        ca = dados.get('classe_processual', '')
        if ' / ' in ca:
            partes = ca.split(' / ', 1)
            dados['classe_processual'] = partes[0].strip()
            dados['assunto_esaj'] = partes[1].strip()

        # ── Ementa ──
        ementa_elem = (
            elem.select_one('div.mensagemSemFormatacao') or
            elem.select_one('td.ementa') or
            elem.select_one('.ementa')
        )
        if ementa_elem:
            dados['ementa'] = ementa_elem.get_text(strip=True)
        else:
            m = re.search(r'Ementa:\s*(.+?)(?:\Z)', texto, re.DOTALL)
            if m:
                dados['ementa'] = m.group(1).strip()[:5000]

        return dados

    # ─── Pipeline de coleta ────────────────────────────────────────────────────

    def coletar(self, termo_busca: str, max_paginas: int = 10,
                classe: str = None, data_inicio: str = None, data_fim: str = None,
                tipo_decisao: str = 'A') -> dict:
        """
        Coleta completa: busca → extrai → salva no banco.
        Retorna dicionário com estatísticas da coleta.
        """
        logger.info(f"Coleta iniciada: '{termo_busca}' (max {max_paginas} pág.)")
        coleta_id = self.db.iniciar_coleta(termo_busca, busca_classe=classe,
                                           data_inicio=data_inicio, data_fim=data_fim)
        self._inicializar_sessao()

        # Primeira página para descobrir total
        html = self.buscar(termo_busca, pagina=1, classe=classe,
                           data_inicio=data_inicio, data_fim=data_fim,
                           tipo_decisao=tipo_decisao)
        total_pags = self._total_paginas(html)
        pags_coletar = min(total_pags, max_paginas)
        logger.info(f"Total de páginas: {total_pags} → coletando {pags_coletar}")

        total_coletados = total_novos = 0

        def _processar(html_pag):
            nonlocal total_coletados, total_novos
            for d in self._extrair_decisoes(html_pag):
                d['coleta_id'] = coleta_id
                resultado = self.db.inserir_decisao(d)
                total_coletados += 1
                if resultado:
                    total_novos += 1

        _processar(html)
        logger.info(f"Pág 1/{pags_coletar}: {total_novos} novas")

        for pag in range(2, pags_coletar + 1):
            try:
                html = self.buscar(termo_busca, pagina=pag, classe=classe,
                                   data_inicio=data_inicio, data_fim=data_fim,
                                   tipo_decisao=tipo_decisao)
                antes = total_novos
                _processar(html)
                logger.info(f"Pág {pag}/{pags_coletar}: {total_novos - antes} novas")
                if total_coletados > 0 and (total_novos - antes) == 0 and pag > 3:
                    logger.info("Sem novidades nas últimas páginas — encerrando antecipadamente.")
                    break
            except Exception as exc:
                logger.error(f"Erro na página {pag}: {exc}")
                self.db.registrar_erro('scraping', str(exc), detalhes=f'pág {pag}')

        self.db.finalizar_coleta(coleta_id, total_pags * 20, total_coletados, total_novos)
        resultado = {
            'coleta_id':       coleta_id,
            'total_paginas':   total_pags,
            'paginas_coletadas': pags_coletar,
            'total_coletados': total_coletados,
            'total_novos':     total_novos,
        }
        logger.info(f"Coleta finalizada: {resultado}")
        return resultado


class PDFDownloader:
    """Baixa PDFs dos acórdãos a partir das URLs coletadas."""

    def __init__(self, config: dict = None):
        self.config  = config or {}
        self.session = requests.Session()
        self.session.headers['User-Agent'] = self.config.get(
            'user_agent', 'JurisprudenciaBot/2.0')
        self.pdf_dir   = self.config.get('pdf_dir', 'data/pdfs')
        self.delay_min = self.config.get('delay_min_segundos', 2)
        self.delay_max = self.config.get('delay_max_segundos', 5)
        self.db        = JurisprudenciaDB(self.config.get('db_path', 'data/jurisprudencia.db'))
        os.makedirs(self.pdf_dir, exist_ok=True)

    def baixar_pendentes(self, limit=100) -> dict:
        pendentes = self.db.pendentes_download(limit)
        logger.info(f"PDFs pendentes: {len(pendentes)}")
        stats = {'total': len(pendentes), 'sucesso': 0, 'erro': 0}

        for item in pendentes:
            time.sleep(random.uniform(self.delay_min, self.delay_max))
            url = item.get('url_acordao')
            if not url:
                continue
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                ct = resp.headers.get('Content-Type', '')
                if 'pdf' in ct.lower() or len(resp.content) > 1000:
                    nome = f"{item['numero_processo'].replace('.','').replace('-','')}.pdf"
                    caminho = os.path.join(self.pdf_dir, nome)
                    with open(caminho, 'wb') as f:
                        f.write(resp.content)
                    self.db.atualizar_pdf(item['numero_processo'], caminho)
                    stats['sucesso'] += 1
                    logger.debug(f"PDF salvo: {item['numero_processo']}")
                else:
                    logger.warning(f"Resposta não é PDF: {item['numero_processo']}")
                    stats['erro'] += 1
            except Exception as exc:
                logger.error(f"Erro ao baixar {item['numero_processo']}: {exc}")
                self.db.registrar_erro('download_pdf', str(exc),
                                       numero_processo=item['numero_processo'],
                                       decisao_id=item['id'])
                stats['erro'] += 1

        logger.info(f"Download concluído: {stats}")
        return stats


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/scraper.log', encoding='utf-8'),
        ]
    )
    os.makedirs('logs', exist_ok=True)

    parser = argparse.ArgumentParser(description='Scraper CJSG/ESAJ TJ-SP')
    parser.add_argument('--busca',    '-b', required=True, help='Termo de busca')
    parser.add_argument('--paginas',  '-p', type=int, default=10)
    parser.add_argument('--classe',   '-c', help='Classe processual')
    parser.add_argument('--data-inicio', help='DD/MM/AAAA')
    parser.add_argument('--data-fim',    help='DD/MM/AAAA')
    parser.add_argument('--tipo', '-t', default='A', choices=['A', 'D', 'H'])
    parser.add_argument('--download-pdfs', action='store_true')
    args = parser.parse_args()

    scraper = CJSGScraper()
    r = scraper.coletar(args.busca, max_paginas=args.paginas, classe=args.classe,
                        data_inicio=args.data_inicio, data_fim=args.data_fim,
                        tipo_decisao=args.tipo)
    print(f"\nColeta: {r['total_novos']} novas de {r['total_coletados']} coletadas")

    if args.download_pdfs:
        PDFDownloader().baixar_pendentes()


if __name__ == '__main__':
    main()
