# JurisIntel v2 — Inteligência Jurisprudencial TJ-SP

Sistema automatizado de coleta, classificação por IA e análise de decisões do Tribunal de Justiça de São Paulo.

## Arquitetura

```
ESAJ/CJSG ──► Scraper ──► PDFs ──► Text Extractor ──► Claude IA ──► SQLite
                                                                       │
                                                          FastAPI ◄────┘
                                                            │
                                                     React Dashboard
```

**Bot Evolutivo**: roda sozinho, aprende com resultados, gera novos termos de busca via IA, desativa termos improdutivos por ROI score.

## Componentes

| Módulo | Descrição |
|---|---|
| `scraper/cjsg_scraper.py` | Coleta no ESAJ com retry, delay e parsing multi-camada |
| `processor/ai_classifier.py` | Classificação via Claude (`claude-sonnet-4-6`) |
| `processor/text_extractor.py` | pdfplumber + OCR Tesseract |
| `processor/drive_sync.py` | Sync Google Drive + Sheets |
| `exports/excel_exporter.py` | Excel formatado com filtros |
| `database/db.py` | SQLite + FTS5 + analytics BI |
| `api/server.py` | FastAPI com 10+ endpoints |
| `bot_evolutivo.py` | Bot autônomo com evolução de termos |
| `run_pipeline.py` | Pipeline completo orquestrado |
| `frontend/` | Dashboard React + Recharts |

## Setup Rápido

```bash
# 1. Ambiente virtual
python -m venv venv && source venv/bin/activate

# 2. Dependências
pip install -r requirements.txt

# 3. Configuração
cp config/config_example.yaml config/config.yaml
# Edite config.yaml com sua ANTHROPIC_API_KEY

# 4. Semear termos iniciais do bot
python bot_evolutivo.py --semear

# 5. Rodar um ciclo de teste
python bot_evolutivo.py --ciclo

# 6. Iniciar API
uvicorn api.server:app --reload --port 8000

# 7. Frontend (dev)
cd frontend && npm install && npm run dev
```

## Docker

```bash
# API + Dashboard
ANTHROPIC_API_KEY=sk-ant-... docker compose up -d

# Com bot noturno
ANTHROPIC_API_KEY=sk-ant-... docker compose --profile bot up -d
```

## API Endpoints

| Endpoint | Descrição |
|---|---|
| `GET /api/stats` | Estatísticas gerais |
| `GET /api/bi` | Payload BI (áreas, tendência, relatores) |
| `GET /api/ranking` | Ranking por taxa de êxito |
| `GET /api/decisoes` | Listagem com filtros |
| `GET /api/decisoes/{id}` | Detalhe de uma decisão |
| `GET /api/busca?q=termo` | Full-text search |
| `GET /api/termos` | Termos ativos do bot |
| `GET /api/ciclos` | Histórico de ciclos |
| `GET /api/relator/{nome}` | Perfil analítico do relator |
| `GET /health` | Health check |

## Bot Evolutivo

```bash
python bot_evolutivo.py --semear                # Inserir 30+ termos-semente
python bot_evolutivo.py --ciclo                 # 1 ciclo completo
python bot_evolutivo.py --ciclos 5              # 5 ciclos seguidos
python bot_evolutivo.py --daemon --horas 8      # Modo noturno (cron)
python bot_evolutivo.py --status                # Ver status e ROI dos termos
python bot_evolutivo.py --adicionar "novo termo" --area "Consumidor"
```

**Score ROI**: `(novos+1) / (usos+1) / prioridade` — termos mais produtivos são pesquisados primeiro.

## Pipeline Manual

```bash
python run_pipeline.py --busca "plano de saúde" --paginas 50 --exportar
python run_pipeline.py --apenas-ia --batch-ia 100
python run_pipeline.py --apenas-exportar --area "Direito do Consumidor"
python run_pipeline.py --stats
```

## Cron Noturno

```bash
bash setup_cron.sh   # Configura o bot para rodar das 22h às 06h
```

## Estrutura

```
├── api/server.py              # FastAPI
├── bot_evolutivo.py           # Bot autônomo
├── run_pipeline.py            # Pipeline orquestrado
├── database/db.py             # SQLite + FTS5 + BI analytics
├── scraper/cjsg_scraper.py    # Scraper ESAJ
├── processor/
│   ├── ai_classifier.py       # Claude claude-sonnet-4-6
│   ├── text_extractor.py      # PDF → texto
│   └── drive_sync.py          # Google Drive/Sheets
├── exports/excel_exporter.py  # Excel formatado
├── frontend/src/              # React + Recharts
├── config/config_example.yaml # Template de configuração
├── Dockerfile                 # Container
└── docker-compose.yml         # API + Bot
```

---

**PBCV Advocacia** — JurisIntel v2 · TJ-SP · Claude AI
