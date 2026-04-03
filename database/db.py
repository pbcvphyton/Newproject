"""
JurisIntel — Módulo de banco de dados (SQLite + FTS5).

Armazena decisões, metadados ESAJ, classificações da IA, termos de busca
e histórico de ciclos do bot. Inclui analytics para o dashboard BI.
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager


class JurisprudenciaDB:
    def __init__(self, db_path: str = "data/jurisprudencia.db"):
        dir_ = os.path.dirname(db_path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-32000")   # 32 MB de cache
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                -- ── Tabela principal ──────────────────────────────────────
                CREATE TABLE IF NOT EXISTS decisoes (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- Identificação ESAJ
                    numero_processo      TEXT UNIQUE NOT NULL,
                    codigo_decisao       TEXT,

                    -- Metadados do ESAJ
                    classe_processual    TEXT,
                    assunto_esaj         TEXT,
                    comarca              TEXT,
                    relator              TEXT,
                    orgao_julgador       TEXT,
                    data_julgamento      DATE,
                    data_publicacao      DATE,
                    data_registro        DATE,
                    ementa               TEXT,
                    url_acordao          TEXT,

                    -- PDF
                    pdf_path             TEXT,
                    pdf_baixado          BOOLEAN DEFAULT 0,
                    texto_extraido       TEXT,
                    texto_extraido_em    DATETIME,

                    -- Classificação IA
                    ia_processado        BOOLEAN DEFAULT 0,
                    ia_processado_em     DATETIME,
                    ia_modelo            TEXT,

                    tipo_acao            TEXT,
                    area_direito         TEXT,
                    tese_principal       TEXT,
                    tese_secundaria      TEXT,
                    resultado            TEXT,
                    resultado_detalhado  TEXT,

                    autor_nome           TEXT,
                    autor_tipo           TEXT,
                    reu_nome             TEXT,
                    reu_tipo             TEXT,

                    valor_causa          REAL,
                    valor_condenacao     REAL,
                    dano_moral_valor     REAL,

                    fundamentacao_legal  TEXT,    -- JSON array
                    precedentes_citados  TEXT,    -- JSON array
                    palavras_chave       TEXT,    -- JSON array

                    resumo_ia            TEXT,
                    observacoes_ia       TEXT,

                    -- Controle
                    coleta_id            INTEGER,
                    criado_em            DATETIME DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em        DATETIME DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (coleta_id) REFERENCES coletas(id)
                );

                -- ── Índices ────────────────────────────────────────────────
                CREATE INDEX IF NOT EXISTS idx_area_direito    ON decisoes(area_direito);
                CREATE INDEX IF NOT EXISTS idx_tipo_acao       ON decisoes(tipo_acao);
                CREATE INDEX IF NOT EXISTS idx_tese_principal  ON decisoes(tese_principal);
                CREATE INDEX IF NOT EXISTS idx_resultado       ON decisoes(resultado);
                CREATE INDEX IF NOT EXISTS idx_reu_tipo        ON decisoes(reu_tipo);
                CREATE INDEX IF NOT EXISTS idx_autor_tipo      ON decisoes(autor_tipo);
                CREATE INDEX IF NOT EXISTS idx_data_julgamento ON decisoes(data_julgamento);
                CREATE INDEX IF NOT EXISTS idx_comarca         ON decisoes(comarca);
                CREATE INDEX IF NOT EXISTS idx_relator         ON decisoes(relator);
                CREATE INDEX IF NOT EXISTS idx_orgao_julgador  ON decisoes(orgao_julgador);
                CREATE INDEX IF NOT EXISTS idx_ia_processado   ON decisoes(ia_processado);
                CREATE INDEX IF NOT EXISTS idx_pdf_baixado     ON decisoes(pdf_baixado);

                -- ── Full-Text Search ───────────────────────────────────────
                CREATE VIRTUAL TABLE IF NOT EXISTS decisoes_fts USING fts5(
                    numero_processo, ementa, texto_extraido,
                    tese_principal, tese_secundaria, resumo_ia, fundamentacao_legal,
                    content=decisoes, content_rowid=id
                );

                CREATE TRIGGER IF NOT EXISTS decisoes_ai AFTER INSERT ON decisoes BEGIN
                    INSERT INTO decisoes_fts(rowid, numero_processo, ementa, texto_extraido,
                        tese_principal, tese_secundaria, resumo_ia, fundamentacao_legal)
                    VALUES (new.id, new.numero_processo, new.ementa, new.texto_extraido,
                        new.tese_principal, new.tese_secundaria, new.resumo_ia,
                        new.fundamentacao_legal);
                END;

                CREATE TRIGGER IF NOT EXISTS decisoes_au AFTER UPDATE ON decisoes BEGIN
                    INSERT INTO decisoes_fts(decisoes_fts, rowid, numero_processo, ementa,
                        texto_extraido, tese_principal, tese_secundaria, resumo_ia,
                        fundamentacao_legal)
                    VALUES ('delete', old.id, old.numero_processo, old.ementa,
                        old.texto_extraido, old.tese_principal, old.tese_secundaria,
                        old.resumo_ia, old.fundamentacao_legal);
                    INSERT INTO decisoes_fts(rowid, numero_processo, ementa, texto_extraido,
                        tese_principal, tese_secundaria, resumo_ia, fundamentacao_legal)
                    VALUES (new.id, new.numero_processo, new.ementa, new.texto_extraido,
                        new.tese_principal, new.tese_secundaria, new.resumo_ia,
                        new.fundamentacao_legal);
                END;

                -- ── Log de coletas ────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS coletas (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    busca_termo          TEXT,
                    busca_classe         TEXT,
                    busca_secao          TEXT,
                    data_inicio_filtro   DATE,
                    data_fim_filtro      DATE,
                    total_resultados     INTEGER,
                    total_coletados      INTEGER,
                    total_novos          INTEGER,
                    iniciado_em          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finalizado_em        DATETIME,
                    status               TEXT DEFAULT 'em_andamento'
                );

                -- ── Log de erros ──────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS erros (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    decisao_id       INTEGER,
                    numero_processo  TEXT,
                    etapa            TEXT,
                    erro             TEXT,
                    detalhes         TEXT,
                    resolvido        BOOLEAN DEFAULT 0,
                    criado_em        DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (decisao_id) REFERENCES decisoes(id)
                );

                -- ── Termos de busca (Bot Evolutivo) ───────────────────────
                CREATE TABLE IF NOT EXISTS termos_busca (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    termo            TEXT UNIQUE NOT NULL,
                    origem           TEXT DEFAULT 'semente',
                    termo_pai_id     INTEGER,
                    area_direito     TEXT,
                    prioridade       INTEGER DEFAULT 5,
                    ativo            BOOLEAN DEFAULT 1,
                    vezes_usado      INTEGER DEFAULT 0,
                    total_resultados INTEGER DEFAULT 0,
                    total_novos      INTEGER DEFAULT 0,
                    ultima_busca     DATETIME,
                    criado_em        DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (termo_pai_id) REFERENCES termos_busca(id)
                );

                CREATE INDEX IF NOT EXISTS idx_termos_ativo     ON termos_busca(ativo);
                CREATE INDEX IF NOT EXISTS idx_termos_prioridade ON termos_busca(prioridade);

                -- ── Ciclos do Bot ─────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS ciclos_bot (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    inicio                DATETIME DEFAULT CURRENT_TIMESTAMP,
                    fim                   DATETIME,
                    status                TEXT DEFAULT 'rodando',
                    termos_pesquisados    INTEGER DEFAULT 0,
                    paginas_coletadas     INTEGER DEFAULT 0,
                    decisoes_novas        INTEGER DEFAULT 0,
                    pdfs_baixados         INTEGER DEFAULT 0,
                    textos_extraidos      INTEGER DEFAULT 0,
                    classificados_ia      INTEGER DEFAULT 0,
                    termos_novos_gerados  INTEGER DEFAULT 0,
                    drive_sincronizado    BOOLEAN DEFAULT 0,
                    log                   TEXT
                );
            """)

    # ─── INSERÇÃO ──────────────────────────────────────────────────────────────

    def inserir_decisao(self, dados: dict) -> int | None:
        with self._conn() as conn:
            try:
                cur = conn.execute("""
                    INSERT OR IGNORE INTO decisoes (
                        numero_processo, codigo_decisao, classe_processual, assunto_esaj,
                        comarca, relator, orgao_julgador, data_julgamento, data_publicacao,
                        data_registro, ementa, url_acordao, coleta_id
                    ) VALUES (
                        :numero_processo, :codigo_decisao, :classe_processual, :assunto_esaj,
                        :comarca, :relator, :orgao_julgador, :data_julgamento, :data_publicacao,
                        :data_registro, :ementa, :url_acordao, :coleta_id
                    )
                """, dados)
                return cur.lastrowid if cur.rowcount > 0 else None
            except sqlite3.IntegrityError:
                return None

    def atualizar_pdf(self, numero_processo: str, pdf_path: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE decisoes SET pdf_path=?, pdf_baixado=1, atualizado_em=? "
                "WHERE numero_processo=?",
                (pdf_path, datetime.now().isoformat(), numero_processo)
            )

    def atualizar_texto(self, numero_processo: str, texto: str):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE decisoes SET texto_extraido=?, texto_extraido_em=?, atualizado_em=? "
                "WHERE numero_processo=?",
                (texto, now, now, numero_processo)
            )

    def atualizar_classificacao_ia(self, numero_processo: str, classificacao: dict):
        for field in ('fundamentacao_legal', 'precedentes_citados', 'palavras_chave'):
            if field in classificacao and isinstance(classificacao[field], list):
                classificacao[field] = json.dumps(classificacao[field], ensure_ascii=False)
        now = datetime.now().isoformat()
        classificacao.update({
            'ia_processado': True,
            'ia_processado_em': now,
            'atualizado_em': now,
            'numero_processo': numero_processo,
        })
        campos = [k for k in classificacao if k != 'numero_processo']
        set_clause = ', '.join(f'{c}=:{c}' for c in campos)
        with self._conn() as conn:
            conn.execute(
                f'UPDATE decisoes SET {set_clause} WHERE numero_processo=:numero_processo',
                classificacao
            )

    # ─── CONSULTAS ─────────────────────────────────────────────────────────────

    def pendentes_download(self, limit=100) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, numero_processo, codigo_decisao, url_acordao "
                "FROM decisoes WHERE pdf_baixado=0 AND url_acordao IS NOT NULL LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def pendentes_extracao(self, limit=100) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, numero_processo, pdf_path "
                "FROM decisoes WHERE pdf_baixado=1 AND texto_extraido IS NULL LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def pendentes_ia(self, limit=50) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, numero_processo, ementa, texto_extraido,
                       classe_processual, assunto_esaj, orgao_julgador, relator
                FROM decisoes
                WHERE ia_processado=0
                  AND (texto_extraido IS NOT NULL OR ementa IS NOT NULL)
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def decisao_por_id(self, decisao_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM decisoes WHERE id=?", (decisao_id,)
            ).fetchone()
            return dict(row) if row else None

    def buscar_fts(self, termos: str, limit=100) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT d.* FROM decisoes d
                JOIN decisoes_fts fts ON d.id=fts.rowid
                WHERE decisoes_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (termos, limit)).fetchall()
            return [dict(r) for r in rows]

    def consultar(self, filtros: dict = None, limit=1000, offset=0) -> list:
        where_clauses, params = [], []
        mapa = {
            'area_direito':   'area_direito=?',
            'tipo_acao':      'tipo_acao=?',
            'tese_principal': 'tese_principal LIKE ?',
            'resultado':      'resultado LIKE ?',
            'reu_tipo':       'reu_tipo LIKE ?',
            'autor_tipo':     'autor_tipo LIKE ?',
            'comarca':        'comarca=?',
            'relator':        'relator LIKE ?',
            'orgao_julgador': 'orgao_julgador LIKE ?',
            'data_inicio':    'data_julgamento>=?',
            'data_fim':       'data_julgamento<=?',
        }
        if filtros:
            for key, clause in mapa.items():
                if filtros.get(key):
                    val = filtros[key]
                    if 'LIKE' in clause and '%' not in val:
                        val = f'%{val}%'
                    where_clauses.append(clause)
                    params.append(val)
        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM decisoes {where} ORDER BY data_julgamento DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── ANALYTICS / BI ────────────────────────────────────────────────────────

    def estatisticas(self) -> dict:
        with self._conn() as conn:
            s = {
                'total':            conn.execute("SELECT COUNT(*) FROM decisoes").fetchone()[0],
                'com_pdf':          conn.execute("SELECT COUNT(*) FROM decisoes WHERE pdf_baixado=1").fetchone()[0],
                'com_texto':        conn.execute("SELECT COUNT(*) FROM decisoes WHERE texto_extraido IS NOT NULL").fetchone()[0],
                'classificados_ia': conn.execute("SELECT COUNT(*) FROM decisoes WHERE ia_processado=1").fetchone()[0],
            }
            s['top_areas'] = [dict(r) for r in conn.execute("""
                SELECT area_direito, COUNT(*) as total FROM decisoes
                WHERE area_direito IS NOT NULL GROUP BY area_direito ORDER BY total DESC LIMIT 10
            """).fetchall()]
            s['top_teses'] = [dict(r) for r in conn.execute("""
                SELECT tese_principal, COUNT(*) as total FROM decisoes
                WHERE tese_principal IS NOT NULL GROUP BY tese_principal ORDER BY total DESC LIMIT 10
            """).fetchall()]
            return s

    def ranking_por_taxa_exito(self) -> list:
        """
        Agrupa por tese/tipo de ação e calcula taxa de êxito.
        Retorna ranking para o dashboard — mínimo 5 decisões por grupo.
        """
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT
                    COALESCE(tese_principal, tipo_acao, 'Não classificado') AS tipo,
                    tipo_acao,
                    area_direito,
                    COUNT(*)  AS total,
                    SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                             THEN 1 ELSE 0 END)  AS pos,
                    SUM(CASE WHEN resultado IN ('não provido','não conhecido','prejudicado')
                             OR resultado IS NULL THEN 1 ELSE 0 END)  AS neg,
                    ROUND(
                        100.0 * SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                                        THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0), 1
                    ) AS taxa,
                    ROUND(AVG(NULLIF(valor_condenacao, 0)), 0)  AS valor_medio_condenacao,
                    ROUND(AVG(NULLIF(dano_moral_valor,  0)), 0) AS dano_moral_medio
                FROM decisoes
                WHERE ia_processado = 1
                  AND (tese_principal IS NOT NULL OR tipo_acao IS NOT NULL)
                GROUP BY COALESCE(tese_principal, tipo_acao)
                HAVING total >= 5
                ORDER BY total DESC, taxa DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def dados_bi(self) -> dict:
        """Payload completo para o dashboard BI — stats, áreas, tendência, relatores."""
        with self._conn() as conn:
            por_area = [dict(r) for r in conn.execute("""
                SELECT
                    area_direito AS name,
                    COUNT(*) AS total,
                    SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                             THEN 1 ELSE 0 END) AS pos,
                    SUM(CASE WHEN resultado NOT IN ('provido','parcialmente provido')
                             OR resultado IS NULL THEN 1 ELSE 0 END) AS neg,
                    ROUND(100.0 * SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                                          THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0), 1) AS taxa
                FROM decisoes
                WHERE area_direito IS NOT NULL AND ia_processado=1
                GROUP BY area_direito ORDER BY total DESC
            """).fetchall()]

            tendencia = [dict(r) for r in conn.execute("""
                SELECT
                    strftime('%Y-%m', data_julgamento) AS mes,
                    COUNT(*) AS total,
                    SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                             THEN 1 ELSE 0 END) AS pos
                FROM decisoes
                WHERE data_julgamento IS NOT NULL AND ia_processado=1
                  AND data_julgamento >= date('now','-12 months')
                GROUP BY mes ORDER BY mes
            """).fetchall()]

            top_relatores = [dict(r) for r in conn.execute("""
                SELECT
                    relator,
                    COUNT(*) AS total,
                    ROUND(100.0 * SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                                          THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0), 1) AS taxa_provido
                FROM decisoes
                WHERE relator IS NOT NULL AND ia_processado=1
                GROUP BY relator HAVING total >= 10
                ORDER BY total DESC LIMIT 20
            """).fetchall()]

            top_tipos = [dict(r) for r in conn.execute("""
                SELECT
                    tipo_acao,
                    COUNT(*) AS total,
                    ROUND(100.0 * SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                                          THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0), 1) AS taxa
                FROM decisoes
                WHERE tipo_acao IS NOT NULL AND ia_processado=1
                GROUP BY tipo_acao ORDER BY total DESC LIMIT 10
            """).fetchall()]

            return {
                'stats':             self.estatisticas(),
                'por_area':          por_area,
                'tendencia_mensal':  tendencia,
                'top_relatores':     top_relatores,
                'top_tipos':         top_tipos,
            }

    def analytics_por_relator(self, relator: str) -> dict:
        """Perfil detalhado de um relator — útil para inteligência de negócio."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                    relator,
                    COUNT(*)  AS total,
                    SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                             THEN 1 ELSE 0 END) AS pos,
                    ROUND(100.0 * SUM(CASE WHEN resultado IN ('provido','parcialmente provido')
                                          THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0), 1) AS taxa_provido,
                    ROUND(AVG(NULLIF(dano_moral_valor, 0)), 0) AS dano_moral_medio,
                    GROUP_CONCAT(DISTINCT area_direito)  AS areas,
                    GROUP_CONCAT(DISTINCT tipo_acao)     AS tipos
                FROM decisoes
                WHERE relator LIKE ? AND ia_processado=1
            """, (f'%{relator}%',)).fetchone()
            return dict(row) if row else {}

    # ─── COLETAS ───────────────────────────────────────────────────────────────

    def iniciar_coleta(self, busca_termo, busca_classe=None, busca_secao=None,
                       data_inicio=None, data_fim=None) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO coletas (busca_termo, busca_classe, busca_secao,
                    data_inicio_filtro, data_fim_filtro)
                VALUES (?,?,?,?,?)
            """, (busca_termo, busca_classe, busca_secao, data_inicio, data_fim))
            return cur.lastrowid

    def finalizar_coleta(self, coleta_id, total_resultados, total_coletados, total_novos):
        with self._conn() as conn:
            conn.execute("""
                UPDATE coletas
                SET total_resultados=?, total_coletados=?, total_novos=?,
                    finalizado_em=?, status='concluida'
                WHERE id=?
            """, (total_resultados, total_coletados, total_novos,
                  datetime.now().isoformat(), coleta_id))

    # ─── ERROS ─────────────────────────────────────────────────────────────────

    def registrar_erro(self, etapa, erro, numero_processo=None, decisao_id=None, detalhes=None):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO erros (decisao_id, numero_processo, etapa, erro, detalhes)
                VALUES (?,?,?,?,?)
            """, (decisao_id, numero_processo, etapa, str(erro), detalhes))

    # ─── TERMOS (BOT EVOLUTIVO) ────────────────────────────────────────────────

    def inserir_termo(self, termo, origem='semente', area=None, prioridade=5, pai_id=None):
        with self._conn() as conn:
            try:
                cur = conn.execute("""
                    INSERT OR IGNORE INTO termos_busca
                        (termo, origem, area_direito, prioridade, termo_pai_id)
                    VALUES (?,?,?,?,?)
                """, (termo.strip(), origem, area, prioridade, pai_id))
                return cur.lastrowid if cur.rowcount > 0 else None
            except sqlite3.IntegrityError:
                return None

    def proximo_termo(self) -> dict | None:
        """
        Seleção por score ROI:
          • Termos novos (nunca usados): ordenados pela prioridade
          • Termos usados: (novos+1)/(usos+1)/prioridade  — favorece os mais produtivos
        """
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM termos_busca WHERE ativo=1
                ORDER BY
                    CASE WHEN vezes_usado=0 THEN 1.0 / prioridade ELSE 0 END DESC,
                    (CAST(total_novos AS REAL) + 1.0) / (vezes_usado + 1.0) / prioridade DESC,
                    criado_em ASC
                LIMIT 1
            """).fetchone()
            return dict(row) if row else None

    def registrar_uso_termo(self, termo_id, total_resultados, total_novos):
        with self._conn() as conn:
            conn.execute("""
                UPDATE termos_busca SET
                    vezes_usado      = vezes_usado + 1,
                    total_resultados = total_resultados + ?,
                    total_novos      = total_novos + ?,
                    ultima_busca     = ?
                WHERE id=?
            """, (total_resultados, total_novos, datetime.now().isoformat(), termo_id))

    def desativar_termo(self, termo_id):
        with self._conn() as conn:
            conn.execute("UPDATE termos_busca SET ativo=0 WHERE id=?", (termo_id,))

    def listar_termos(self, ativos=True) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM termos_busca WHERE ativo=?
                ORDER BY
                    (CAST(total_novos AS REAL) + 1.0) / (vezes_usado + 1.0) / prioridade DESC
            """, (1 if ativos else 0,)).fetchall()
            return [dict(r) for r in rows]

    def total_termos(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM termos_busca WHERE ativo=1"
            ).fetchone()[0]

    def ementas_recentes(self, limit=100) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT ementa, classe_processual, assunto_esaj, tese_principal, area_direito
                FROM decisoes
                WHERE ementa IS NOT NULL AND ia_processado=1
                ORDER BY criado_em DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def termos_existentes(self) -> set:
        with self._conn() as conn:
            rows = conn.execute("SELECT termo FROM termos_busca").fetchall()
            return {r[0].lower() for r in rows}

    # ─── CICLOS DO BOT ─────────────────────────────────────────────────────────

    def iniciar_ciclo(self) -> int:
        with self._conn() as conn:
            cur = conn.execute("INSERT INTO ciclos_bot DEFAULT VALUES")
            return cur.lastrowid

    def atualizar_ciclo(self, ciclo_id, **kwargs):
        with self._conn() as conn:
            sets = ', '.join(f'{k}=?' for k in kwargs)
            conn.execute(
                f"UPDATE ciclos_bot SET {sets} WHERE id=?",
                list(kwargs.values()) + [ciclo_id]
            )

    def finalizar_ciclo(self, ciclo_id, **stats):
        stats.update({'fim': datetime.now().isoformat(), 'status': 'concluido'})
        self.atualizar_ciclo(ciclo_id, **stats)

    def ultimo_ciclo(self) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ciclos_bot ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def historico_ciclos(self, limit=30) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM ciclos_bot WHERE status='concluido'
                ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]


if __name__ == '__main__':
    db = JurisprudenciaDB()
    print('Banco inicializado com sucesso.')
    print(db.estatisticas())
