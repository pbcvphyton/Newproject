"""
JurisIntel — API Server (FastAPI)

Expõe todos os dados do banco para o dashboard React e integrações externas.

Endpoints:
  GET  /api/stats                  — estatísticas gerais
  GET  /api/bi                     — payload completo para o dashboard BI
  GET  /api/ranking                — ranking por taxa de êxito
  GET  /api/decisoes               — listagem com filtros
  GET  /api/decisoes/{id}          — detalhe de uma decisão
  GET  /api/busca?q=termo          — full-text search
  GET  /api/termos                 — termos ativos do bot
  GET  /api/ciclos                 — histórico de ciclos do bot
  GET  /api/relator/{nome}         — perfil analítico de um relator
  GET  /health                     — health check

Inicia com:
  uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
  ou:
  python api/server.py
"""

import os
import sys
import logging
from typing import Optional

import yaml
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import JurisprudenciaDB

logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title='JurisIntel API — TJ-SP',
    description='Inteligência jurisprudencial automatizada para o TJSP',
    version='2.0.0',
    docs_url='/api/docs',
    redoc_url='/api/redoc',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _config() -> dict:
    path = 'config/config.yaml'
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _db() -> JurisprudenciaDB:
    db_path = _config().get('database', {}).get('path', 'data/jurisprudencia.db')
    return JurisprudenciaDB(db_path)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get('/health')
def health():
    """Health check — verifica conexão com o banco."""
    try:
        db    = _db()
        stats = db.estatisticas()
        return {'status': 'ok', 'decisoes': stats['total']}
    except Exception as exc:
        return JSONResponse(status_code=503, content={'status': 'error', 'detail': str(exc)})


@app.get('/api/stats')
def get_stats():
    """Estatísticas gerais do banco."""
    return _db().estatisticas()


@app.get('/api/bi')
def get_bi():
    """Payload completo para o dashboard BI: stats, áreas, tendência, relatores."""
    return _db().dados_bi()


@app.get('/api/ranking')
def get_ranking():
    """Ranking de teses/tipos de ação por taxa de êxito (mín. 5 decisões)."""
    return _db().ranking_por_taxa_exito()


@app.get('/api/decisoes')
def get_decisoes(
    area:        Optional[str] = None,
    tipo_acao:   Optional[str] = None,
    tese:        Optional[str] = None,
    resultado:   Optional[str] = None,
    reu_tipo:    Optional[str] = None,
    autor_tipo:  Optional[str] = None,
    comarca:     Optional[str] = None,
    relator:     Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim:    Optional[str] = None,
    limit:  int = Query(100, le=2000, description='Máx. 2000 por requisição'),
    offset: int = Query(0,   ge=0),
):
    """Lista decisões com filtros opcionais."""
    filtros = {}
    if area:        filtros['area_direito']  = area
    if tipo_acao:   filtros['tipo_acao']     = tipo_acao
    if tese:        filtros['tese_principal'] = tese
    if resultado:   filtros['resultado']     = resultado
    if reu_tipo:    filtros['reu_tipo']      = reu_tipo
    if autor_tipo:  filtros['autor_tipo']    = autor_tipo
    if comarca:     filtros['comarca']       = comarca
    if relator:     filtros['relator']       = relator
    if data_inicio: filtros['data_inicio']   = data_inicio
    if data_fim:    filtros['data_fim']      = data_fim
    return _db().consultar(filtros=filtros if filtros else None,
                           limit=limit, offset=offset)


@app.get('/api/decisoes/{decisao_id}')
def get_decisao(decisao_id: int):
    """Detalhe completo de uma decisão pelo ID."""
    d = _db().decisao_por_id(decisao_id)
    if not d:
        raise HTTPException(status_code=404, detail='Decisão não encontrada')
    return d


@app.get('/api/busca')
def busca_fts(
    q:     str = Query(..., description='Termo de busca full-text'),
    limit: int = Query(50, le=500),
):
    """Busca full-text no conteúdo das ementas e textos extraídos."""
    return _db().buscar_fts(q, limit=limit)


@app.get('/api/termos')
def get_termos(ativos: bool = True):
    """Termos de busca do bot evolutivo com score ROI."""
    db     = _db()
    termos = db.listar_termos(ativos=ativos)
    # Adiciona score ROI calculado
    for t in termos:
        t['roi_score'] = round(
            (t['total_novos'] + 1) / (t['vezes_usado'] + 1) / t['prioridade'], 3
        )
    return termos


@app.get('/api/ciclos')
def get_ciclos(limit: int = Query(20, le=100)):
    """Histórico dos ciclos de execução do bot."""
    db = _db()
    return {
        'ultimo':    db.ultimo_ciclo(),
        'historico': db.historico_ciclos(limit=limit),
        'stats':     db.estatisticas(),
    }


@app.get('/api/relator/{nome}')
def get_relator(nome: str):
    """Perfil analítico de um relator — taxa de provimento, áreas, valor médio."""
    r = _db().analytics_por_relator(nome)
    if not r or not r.get('total'):
        raise HTTPException(status_code=404,
                            detail=f"Relator '{nome}' não encontrado ou sem dados suficientes")
    return r


# ── Serve frontend React (após build) ─────────────────────────────────────────
_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
if os.path.exists(_FRONTEND_DIST):
    app.mount('/', StaticFiles(directory=_FRONTEND_DIST, html=True), name='frontend')
    logger.info(f"Frontend servido de: {_FRONTEND_DIST}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn
    cfg     = _config()
    api_cfg = cfg.get('api', {})
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    uvicorn.run(
        'api.server:app',
        host    = api_cfg.get('host', '0.0.0.0'),
        port    = api_cfg.get('port', 8000),
        reload  = False,
        workers = 1,
    )
