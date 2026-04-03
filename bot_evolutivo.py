"""
JurisIntel — Bot Evolutivo de Jurisprudência

O bot que roda sozinho, aprende com os resultados e mapeia o judiciário paulista.

CICLO DE EVOLUÇÃO:
  1. Seleciona próximos termos por score ROI  (novos+1)/(usos+1)/prioridade
  2. Pesquisa no ESAJ, coleta decisões, baixa PDFs
  3. Extrai texto, classifica com IA (Claude)
  4. Analisa ementas classificadas → gera NOVOS termos de busca
  5. Desativa termos esgotados (N ciclos sem novidades)
  6. Repete — ideal para rodar à noite via cron

Bugs corrigidos vs versão original:
  - Modelo atualizado para claude-sonnet-4-6
  - Seleção de termos agora usa score ROI (não só prioridade)

Uso:
  python bot_evolutivo.py --semear                 # sementes iniciais
  python bot_evolutivo.py --ciclo                  # 1 ciclo
  python bot_evolutivo.py --ciclos 5               # 5 ciclos
  python bot_evolutivo.py --daemon --horas 8       # modo noturno
  python bot_evolutivo.py --status                 # ver status
  python bot_evolutivo.py --adicionar "termo novo" # termo manual
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database.db import JurisprudenciaDB
from scraper.cjsg_scraper import CJSGScraper, PDFDownloader
from processor.text_extractor import processar_pendentes as extrair_textos
from processor.ai_classifier import AIClassifier

logger = logging.getLogger('bot')

# ─── Termos-semente ────────────────────────────────────────────────────────────
SEMENTES = [
    # Consumidor
    ("negativação indevida dano moral",           "Consumidor",  1),
    ("plano saúde negativa cobertura",            "Consumidor",  1),
    ("falha prestação serviço indenização",        "Consumidor",  2),
    ("cobrança indevida repetição dobro",          "Consumidor",  2),
    ("vício produto consumidor indenização",       "Consumidor",  3),
    ("propaganda enganosa consumidor dano moral",  "Consumidor",  4),
    # Bancário
    ("revisional contrato bancário juros abusivos","Bancário",    1),
    ("tarifa bancária ilegal restituição",         "Bancário",    2),
    ("busca apreensão alienação fiduciária",       "Bancário",    2),
    ("seguro prestamista venda casada nulidade",   "Bancário",    3),
    ("empréstimo consignado fraude indevido",      "Bancário",    3),
    ("capitalização juros abusividade banco",      "Bancário",    4),
    # Imobiliário
    ("distrato imobiliário atraso entrega",        "Imobiliário", 1),
    ("construtora rescisão contratual devolução",  "Imobiliário", 2),
    ("condomínio despesas cobrança inadimplência", "Imobiliário", 3),
    ("locação despejo inadimplência",              "Imobiliário", 3),
    ("incorporadora atraso obra indenização",      "Imobiliário", 3),
    # Família
    ("revisão alimentos necessidade possibilidade","Família",     2),
    ("guarda compartilhada melhor interesse",      "Família",     3),
    ("divórcio partilha bens",                     "Família",     3),
    ("alienação parental indenização",             "Família",     4),
    # Civil
    ("responsabilidade civil dano moral",          "Civil",       2),
    ("erro médico indenização",                    "Civil",       2),
    ("acidente trânsito indenização dano",         "Civil",       3),
    ("dano material lucros cessantes",             "Civil",       3),
    # Público
    ("responsabilidade civil estado omissão",      "Público",     2),
    ("fazenda pública indenização dano",           "Público",     3),
    ("concurso público nomeação preterição",       "Público",     4),
    # Empresarial
    ("dissolução sociedade apuração haveres",      "Empresarial", 3),
    ("recuperação judicial crédito habilitação",   "Empresarial", 3),
    # Tributário
    ("execução fiscal prescrição intercorrente",   "Tributário",  3),
    ("ICMS substituição tributária restituição",   "Tributário",  4),
]

# ─── Prompt de evolução ────────────────────────────────────────────────────────
EVOLUCAO_PROMPT = """Você é um analista jurídico especializado em jurisprudência do TJ-SP.

Analise as ementas abaixo e gere NOVOS termos de busca para coletar mais decisões relevantes no ESAJ.

REGRAS:
1. Entre 5 e 15 novos termos
2. Cada termo: 3 a 6 palavras (funciona melhor no ESAJ)
3. NÃO repita os termos já existentes
4. Priorize: teses específicas recorrentes, tipos de ação com volume potencial, áreas sub-representadas
5. Para cada termo: área do direito e prioridade (1=altíssima, 3=média, 5=baixa)

TERMOS JÁ EXISTENTES (NÃO REPETIR):
{termos_existentes}

EMENTAS RECENTES:
{ementas}

RESPONDA APENAS em JSON (sem markdown):
[
  {{"termo": "...", "area": "...", "prioridade": 2, "motivo": "..."}},
  ...
]"""


def _load_config(path='config/config.yaml') -> dict:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


class BotEvolutivo:
    """Bot autônomo que coleta, classifica e evolui pesquisas de jurisprudência."""

    def __init__(self, config_path='config/config.yaml'):
        self.config = _load_config(config_path)
        db_path = self.config.get('database', {}).get('path', 'data/jurisprudencia.db')
        self.db = JurisprudenciaDB(db_path)

        scraper_cfg = {**self.config.get('scraper', {}), 'db_path': db_path}
        self.scraper    = CJSGScraper(scraper_cfg)
        self.downloader = PDFDownloader(scraper_cfg)

        bot_cfg = self.config.get('bot', {})
        self.paginas_por_termo              = bot_cfg.get('paginas_por_termo', 15)
        self.max_pdfs_por_ciclo             = bot_cfg.get('max_pdfs_por_ciclo', 100)
        self.max_ia_por_ciclo               = bot_cfg.get('max_ia_por_ciclo', 50)
        self.max_termos_por_ciclo           = bot_cfg.get('max_termos_por_ciclo', 5)
        self.ciclos_sem_novos_para_desativar = bot_cfg.get('ciclos_sem_novos_para_desativar', 3)

        self.classifier = None
        try:
            ai_cfg = {**self.config.get('anthropic', {}), 'db_path': db_path}
            self.classifier = AIClassifier(ai_cfg)
        except ValueError as exc:
            logger.warning(f"IA indisponível: {exc}")

    # ─── Semeadura ────────────────────────────────────────────────────────────

    def semear(self) -> int:
        """Insere os termos-semente no banco."""
        total = sum(
            1 for termo, area, prio in SEMENTES
            if self.db.inserir_termo(termo, origem='semente', area=area, prioridade=prio)
        )
        logger.info(f"Semeadura: {total} novos termos inseridos")
        print(f"✓ {total} termos-semente inseridos")
        return total

    # ─── Ciclo principal ──────────────────────────────────────────────────────

    def executar_ciclo(self) -> dict:
        """Executa um ciclo completo: coleta → PDFs → texto → IA → evolução."""
        ciclo_id = self.db.iniciar_ciclo()
        stats = {k: 0 for k in (
            'termos_pesquisados', 'paginas_coletadas', 'decisoes_novas',
            'pdfs_baixados', 'textos_extraidos', 'classificados_ia', 'termos_novos_gerados',
        )}
        logger.info(f"{'='*55}")
        logger.info(f"CICLO #{ciclo_id} — {datetime.now():%d/%m/%Y %H:%M}")
        logger.info(f"{'='*55}")
        try:
            stats.update(self._fase_coleta())
            stats.update(self._fase_download())
            stats.update(self._fase_extracao())
            stats.update(self._fase_classificacao())
            stats.update(self._fase_evolucao())
            self.db.finalizar_ciclo(ciclo_id, **stats)
        except Exception as exc:
            logger.error(f"Erro no ciclo #{ciclo_id}: {exc}")
            self.db.atualizar_ciclo(ciclo_id, status='erro', log=str(exc),
                                    fim=datetime.now().isoformat())
            raise
        self._print_ciclo(ciclo_id, stats)
        return stats

    def _fase_coleta(self) -> dict:
        logger.info("── FASE 1: COLETA ──")
        stats = {'termos_pesquisados': 0, 'paginas_coletadas': 0, 'decisoes_novas': 0}

        # Contador de ciclos sem novos por termo (em memória)
        for _ in range(self.max_termos_por_ciclo):
            t = self.db.proximo_termo()
            if not t:
                logger.warning("Sem termos disponíveis. Execute --semear.")
                break

            logger.info(f"  Pesquisando: '{t['termo']}' "
                        f"(prio={t['prioridade']}, usos={t['vezes_usado']}, "
                        f"ROI={( (t['total_novos']+1)/(t['vezes_usado']+1) ):.2f})")
            try:
                r = self.scraper.coletar(t['termo'],
                                         max_paginas=self.paginas_por_termo)
                self.db.registrar_uso_termo(t['id'],
                                            total_resultados=r['total_coletados'],
                                            total_novos=r['total_novos'])
                stats['termos_pesquisados']  += 1
                stats['paginas_coletadas']   += r['paginas_coletadas']
                stats['decisoes_novas']      += r['total_novos']
                logger.info(f"  → {r['total_novos']} novas de {r['total_coletados']}")

                # Desativar se esgotado (usa vezes_usado pós-atualização)
                if t['vezes_usado'] + 1 >= self.ciclos_sem_novos_para_desativar \
                        and r['total_novos'] == 0:
                    self.db.desativar_termo(t['id'])
                    logger.info(f"  → Termo desativado (esgotado): '{t['termo']}'")

            except Exception as exc:
                logger.error(f"  Erro ao coletar '{t['termo']}': {exc}")
                self.db.registrar_erro('scraping', str(exc), detalhes=f"termo: {t['termo']}")

        return stats

    def _fase_download(self) -> dict:
        logger.info("── FASE 2: DOWNLOAD PDFs ──")
        r = self.downloader.baixar_pendentes(limit=self.max_pdfs_por_ciclo)
        logger.info(f"  → {r['sucesso']} baixados")
        return {'pdfs_baixados': r['sucesso']}

    def _fase_extracao(self) -> dict:
        logger.info("── FASE 3: EXTRAÇÃO DE TEXTO ──")
        r = extrair_textos(db_path=self.db.db_path, limit=self.max_pdfs_por_ciclo)
        logger.info(f"  → {r['sucesso']} extraídos")
        return {'textos_extraidos': r['sucesso']}

    def _fase_classificacao(self) -> dict:
        logger.info("── FASE 4: CLASSIFICAÇÃO IA ──")
        if not self.classifier:
            logger.info("  → Pulada (IA não configurada)")
            return {'classificados_ia': 0}
        r = self.classifier.processar_pendentes(limit=self.max_ia_por_ciclo, delay=1.5)
        logger.info(f"  → {r['sucesso']} classificadas")
        return {'classificados_ia': r['sucesso']}

    def _fase_evolucao(self) -> dict:
        """O cérebro do bot: analisa ementas e gera novos termos de busca."""
        logger.info("── FASE 5: EVOLUÇÃO DE TERMOS ──")
        if not self.classifier:
            logger.info("  → Pulada (IA não configurada)")
            return {'termos_novos_gerados': 0}

        ementas_raw = self.db.ementas_recentes(limit=100)
        if len(ementas_raw) < 10:
            logger.info("  → Poucas ementas ainda. Continuando coleta.")
            return {'termos_novos_gerados': 0}

        ementas_texto = []
        for e in ementas_raw[:50]:
            partes = []
            if e.get('area_direito'):    partes.append(f"Área: {e['area_direito']}")
            if e.get('tese_principal'):  partes.append(f"Tese: {e['tese_principal']}")
            ementa = (e.get('ementa') or '')[:300]
            if ementa:                   partes.append(f"Ementa: {ementa}")
            ementas_texto.append(' | '.join(partes))

        termos_existentes = self.db.termos_existentes()
        prompt = EVOLUCAO_PROMPT.format(
            termos_existentes='\n'.join(f'- {t}' for t in sorted(termos_existentes)),
            ementas='\n---\n'.join(ementas_texto),
        )

        try:
            import anthropic
            api_key = (self.config.get('anthropic', {}).get('api_key')
                       or os.environ.get('ANTHROPIC_API_KEY'))
            model   = self.config.get('anthropic', {}).get('model', 'claude-sonnet-4-6')
            client  = anthropic.Anthropic(api_key=api_key)

            resp  = client.messages.create(
                model=model, max_tokens=2000,
                messages=[{'role': 'user', 'content': prompt}],
            )
            texto = resp.content[0].text.strip()
            # Limpar fence markdown se houver
            if texto.startswith('```'):
                linhas = texto.splitlines()
                texto  = '\n'.join(linhas[1:-1] if linhas[-1].strip() == '```'
                                   else linhas[1:])

            novos = json.loads(texto)
            total = 0
            for item in novos:
                termo = (item.get('termo') or '').strip()
                if not termo or termo.lower() in termos_existentes:
                    continue
                inserted = self.db.inserir_termo(
                    termo=termo,
                    origem='ia_evolucao',
                    area=item.get('area'),
                    prioridade=item.get('prioridade', 5),
                )
                if inserted:
                    total += 1
                    logger.info(f"  + Novo termo: '{termo}' "
                                f"({item.get('area')}, prio={item.get('prioridade')})")
                    logger.debug(f"    Motivo: {item.get('motivo','—')}")

            logger.info(f"  → {total} novos termos gerados")
            return {'termos_novos_gerados': total}

        except Exception as exc:
            logger.error(f"Erro na evolução: {exc}")
            return {'termos_novos_gerados': 0}

    # ─── Daemon ───────────────────────────────────────────────────────────────

    def rodar_daemon(self, horas=8, intervalo_min=10):
        """Loop contínuo por N horas — ideal para cron noturno."""
        fim = datetime.now() + timedelta(hours=horas)
        ciclo_n = 0
        logger.info(f"Daemon iniciado — até {fim:%H:%M}")
        print(f"🤖 Bot em modo daemon — {horas}h (até {fim:%H:%M})")

        while datetime.now() < fim:
            ciclo_n += 1
            try:
                self.executar_ciclo()
            except Exception as exc:
                logger.error(f"Ciclo {ciclo_n} falhou: {exc}")
                time.sleep(60)
                continue
            if datetime.now() < fim:
                logger.info(f"Aguardando {intervalo_min} min…")
                time.sleep(intervalo_min * 60)

        print(f"🤖 Bot encerrado — {ciclo_n} ciclos executados")

    # ─── Status ───────────────────────────────────────────────────────────────

    def status(self):
        stats  = self.db.estatisticas()
        termos = self.db.listar_termos(ativos=True)
        ultimo = self.db.ultimo_ciclo()

        print(f"""
╔══════════════════════════════════════════════════════════╗
║           🤖 JurisIntel — Bot Evolutivo v2              ║
╠══════════════════════════════════════════════════════════╣
║  BANCO DE DADOS                                         ║
║  Decisões coletadas:      {stats['total']:>8}                    ║
║  Com PDF baixado:         {stats['com_pdf']:>8}                    ║
║  Com texto extraído:      {stats['com_texto']:>8}                    ║
║  Classificados pela IA:   {stats['classificados_ia']:>8}                    ║
╠══════════════════════════════════════════════════════════╣
║  TERMOS ATIVOS:           {len(termos):>8}                    ║
╚══════════════════════════════════════════════════════════╝""")

        if ultimo:
            print(f"\nÚLTIMO CICLO (#{ultimo['id']}) — {ultimo['status']}")
            print(f"  Novas: {ultimo.get('decisoes_novas',0)} | "
                  f"PDFs: {ultimo.get('pdfs_baixados',0)} | "
                  f"IA: {ultimo.get('classificados_ia',0)} | "
                  f"Termos gerados: {ultimo.get('termos_novos_gerados',0)}")

        if termos:
            print(f"\n{'ROI':>6} {'Prio':>4} {'Usos':>5} {'Novos':>6}  Termo")
            print('─' * 70)
            for t in termos[:15]:
                roi = (t['total_novos'] + 1) / (t['vezes_usado'] + 1)
                print(f"{roi:6.2f} {t['prioridade']:>4} {t['vezes_usado']:>5} "
                      f"{t['total_novos']:>6}  {t['termo']}")

    def _print_ciclo(self, ciclo_id, stats):
        print(f"""
┌─────────────────────────────────────────────┐
│  Ciclo #{ciclo_id} concluído                         │
├─────────────────────────────────────────────┤
│  Termos pesquisados:    {stats['termos_pesquisados']:>6}               │
│  Decisões novas:        {stats['decisoes_novas']:>6}               │
│  PDFs baixados:         {stats['pdfs_baixados']:>6}               │
│  Textos extraídos:      {stats['textos_extraidos']:>6}               │
│  Classificados IA:      {stats['classificados_ia']:>6}               │
│  Novos termos (IA):     {stats['termos_novos_gerados']:>6}               │
└─────────────────────────────────────────────┘""")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/bot_{datetime.now():%Y%m%d}.log', encoding='utf-8'),
        ]
    )
    parser = argparse.ArgumentParser(description='🤖 Bot Evolutivo — JurisIntel')
    parser.add_argument('--semear',    action='store_true', help='Inserir termos-semente')
    parser.add_argument('--ciclo',     action='store_true', help='Executar 1 ciclo')
    parser.add_argument('--ciclos',    type=int,            help='Executar N ciclos')
    parser.add_argument('--daemon',    action='store_true', help='Modo loop contínuo')
    parser.add_argument('--horas',     type=float, default=8)
    parser.add_argument('--status',    action='store_true')
    parser.add_argument('--adicionar', help='Adicionar termo manual')
    parser.add_argument('--area',      help='Área (com --adicionar)')
    parser.add_argument('--config',    default='config/config.yaml')
    args = parser.parse_args()

    bot = BotEvolutivo(args.config)

    if args.status:
        bot.status()
    elif args.semear:
        bot.semear()
        bot.status()
    elif args.ciclo:
        bot.executar_ciclo()
    elif args.ciclos:
        for i in range(args.ciclos):
            print(f"\n🔄 Ciclo {i+1}/{args.ciclos}")
            bot.executar_ciclo()
            if i < args.ciclos - 1:
                time.sleep(30)
    elif args.daemon:
        bot.rodar_daemon(horas=args.horas)
    elif args.adicionar:
        r = bot.db.inserir_termo(args.adicionar, origem='manual',
                                 area=args.area, prioridade=3)
        print(f"{'✓ Adicionado' if r else '⚠ Já existe'}: '{args.adicionar}'")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
