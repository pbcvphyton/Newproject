"""
JurisIntel — Pipeline Completo

Orquestra: Coleta → Download PDF → Extração → Classificação IA → Exportação → Drive Sync

Uso:
  python run_pipeline.py --busca "plano de saúde" --paginas 50
  python run_pipeline.py --busca "dano moral" --paginas 100 --exportar
  python run_pipeline.py --apenas-ia --batch-ia 200
  python run_pipeline.py --apenas-exportar --area "Direito do Consumidor"
  python run_pipeline.py --stats
"""

import os
import sys
import logging
import argparse
from datetime import datetime

import yaml

from scraper.cjsg_scraper import CJSGScraper, PDFDownloader
from processor.text_extractor import processar_pendentes as extrair_textos
from processor.ai_classifier import AIClassifier
from exports.excel_exporter import exportar_excel
from database.db import JurisprudenciaDB

try:
    from processor.drive_sync import GoogleDriveSync, GoogleSheetsSync, GOOGLE_API_AVAILABLE
except ImportError:
    GOOGLE_API_AVAILABLE = False


def _load_config(path='config/config.yaml') -> dict:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _setup_logging(config: dict):
    log_dir = config.get('logging', {}).get('log_dir', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    level = getattr(logging, config.get('logging', {}).get('level', 'INFO'))
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(log_dir, f'pipeline_{datetime.now():%Y%m%d}.log'),
                encoding='utf-8'
            ),
        ]
    )


def print_stats(db: JurisprudenciaDB):
    s = db.estatisticas()
    print(f"""
╔══════════════════════════════════════════════════╗
║       BANCO DE DADOS — JURISPRUDÊNCIA TJ-SP     ║
╠══════════════════════════════════════════════════╣
║  Total de decisões:       {s['total']:>8}              ║
║  Com PDF baixado:         {s['com_pdf']:>8}              ║
║  Com texto extraído:      {s['com_texto']:>8}              ║
║  Classificados pela IA:   {s['classificados_ia']:>8}              ║
╚══════════════════════════════════════════════════╝""")
    if s.get('top_areas'):
        print("\nTOP ÁREAS:")
        for item in s['top_areas']:
            print(f"  {item['area_direito']:40s} {item['total']:>5}")
    if s.get('top_teses'):
        print("\nTOP TESES:")
        for item in s['top_teses']:
            print(f"  {item['tese_principal']:40s} {item['total']:>5}")


def run_pipeline(args, config):
    log = logging.getLogger('pipeline')
    db_path = config.get('database', {}).get('path', 'data/jurisprudencia.db')
    db = JurisprudenciaDB(db_path)

    # ── Passo 1: Coleta ───────────────────────────────────────────────────────
    if args.busca and not args.apenas_ia and not args.apenas_exportar:
        log.info('=' * 55)
        log.info('PASSO 1: COLETA')
        scraper_cfg = {**config.get('scraper', {}), 'db_path': db_path}
        r = CJSGScraper(scraper_cfg).coletar(
            termo_busca=args.busca, max_paginas=args.paginas,
            classe=args.classe, data_inicio=args.data_inicio, data_fim=args.data_fim,
        )
        print(f"\n✓ Coleta: {r['total_novos']} novas ({r['total_coletados']} coletadas)")

    # ── Passo 2: Download de PDFs ─────────────────────────────────────────────
    if not args.pular_pdf and not args.apenas_ia and not args.apenas_exportar:
        log.info('PASSO 2: DOWNLOAD PDFs')
        dl_cfg = {**config.get('scraper', {}), 'db_path': db_path}
        r = PDFDownloader(dl_cfg).baixar_pendentes(limit=args.batch_pdf)
        print(f"✓ PDFs: {r['sucesso']} baixados, {r['erro']} erros")

        log.info('PASSO 3: EXTRAÇÃO DE TEXTO')
        r = extrair_textos(db_path=db_path, limit=500)
        print(f"✓ Textos: {r['sucesso']} extraídos, {r['erro']} erros")

    # ── Passo 4: Classificação IA ─────────────────────────────────────────────
    if not args.pular_ia and not args.apenas_exportar:
        log.info('PASSO 4: CLASSIFICAÇÃO IA')
        ai_cfg = {**config.get('anthropic', {}), 'db_path': db_path}
        try:
            r = AIClassifier(ai_cfg).processar_pendentes(
                limit=args.batch_ia, delay=args.delay_ia)
            print(f"✓ IA: {r['sucesso']} classificados, {r['erro']} erros")
        except ValueError as exc:
            print(f"⚠ IA pulada: {exc}")

    # ── Passo 5: Exportação ───────────────────────────────────────────────────
    output_path = None
    if args.exportar or args.apenas_exportar:
        log.info('PASSO 5: EXPORTAÇÃO')
        filtros = {}
        if args.area: filtros['area_direito'] = args.area
        if args.tese: filtros['tese_principal'] = args.tese
        decisoes = db.consultar(filtros=filtros if filtros else None, limit=50000)
        if decisoes:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_dir = config.get('exports', {}).get('output_dir', 'data/exports')
            os.makedirs(export_dir, exist_ok=True)
            output_path = os.path.join(export_dir, f'jurisprudencia_{ts}.xlsx')
            exportar_excel(decisoes, output_path)
            print(f"✓ Exportado: {output_path} ({len(decisoes)} decisões)")
        else:
            print("⚠ Nenhuma decisão para exportar")

    # ── Passo 6: Sync Google Drive ────────────────────────────────────────────
    if GOOGLE_API_AVAILABLE and not args.pular_drive:
        log.info('PASSO 6: GOOGLE DRIVE')
        try:
            drive = GoogleDriveSync()
            drive.backup_database(db_path)
            pdf_dir = config.get('scraper', {}).get('pdf_dir', 'data/pdfs')
            r = drive.sync_all_pdfs(pdf_dir)
            print(f"✓ Drive: {r['enviados']} PDFs sincronizados, backup enviado")
            if output_path and os.path.exists(output_path):
                drive.upload_export(output_path)
                print("✓ Excel enviado ao Drive")
        except Exception as exc:
            print(f"⚠ Drive: {exc}")

    print_stats(db)


def main():
    parser = argparse.ArgumentParser(
        description='JurisIntel — Pipeline TJ-SP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Coleta
    parser.add_argument('--busca',       '-b')
    parser.add_argument('--paginas',     '-p', type=int, default=10)
    parser.add_argument('--classe',      help='Classe processual')
    parser.add_argument('--data-inicio', dest='data_inicio')
    parser.add_argument('--data-fim',    dest='data_fim')
    # PDF
    parser.add_argument('--pular-pdf',   dest='pular_pdf',  action='store_true')
    parser.add_argument('--batch-pdf',   dest='batch_pdf',  type=int, default=100)
    # IA
    parser.add_argument('--pular-ia',    dest='pular_ia',   action='store_true')
    parser.add_argument('--apenas-ia',   dest='apenas_ia',  action='store_true')
    parser.add_argument('--batch-ia',    dest='batch_ia',   type=int,   default=50)
    parser.add_argument('--delay-ia',    dest='delay_ia',   type=float, default=1.0)
    # Exportação
    parser.add_argument('--exportar',       '-e', action='store_true')
    parser.add_argument('--apenas-exportar', dest='apenas_exportar', action='store_true')
    parser.add_argument('--area')
    parser.add_argument('--tese')
    # Outros
    parser.add_argument('--pular-drive', dest='pular_drive', action='store_true')
    parser.add_argument('--stats',       action='store_true')
    parser.add_argument('--config',      default='config/config.yaml')
    args = parser.parse_args()

    config = _load_config(args.config)
    _setup_logging(config)

    if args.stats:
        db = JurisprudenciaDB(config.get('database', {}).get('path', 'data/jurisprudencia.db'))
        print_stats(db)
        return

    if not any([args.busca, args.apenas_ia, args.apenas_exportar]):
        parser.print_help()
        return

    run_pipeline(args, config)


if __name__ == '__main__':
    main()
