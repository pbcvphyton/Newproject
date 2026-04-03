"""
JurisIntel — Classificador de decisões por IA (Claude API).

Envia ementa + inteiro teor para o Claude e recebe JSON estruturado com:
tipo de ação, área do direito, teses, partes, resultado, valores, precedentes.

Bugs corrigidos vs versão original:
  - Modelo atualizado para claude-sonnet-4-6
  - Retry automático em falhas de JSON parsing
  - Limpeza mais robusta de artefatos markdown na resposta
"""

import json
import logging
import argparse
import os
import sys
import time

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import JurisprudenciaDB

logger = logging.getLogger(__name__)

# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um analista jurídico especializado em jurisprudência do Tribunal de Justiça de São Paulo (TJ-SP).

Analise decisões judiciais (acórdãos) e extraia informações estruturadas.

RESPONDA EXCLUSIVAMENTE em formato JSON válido, sem nenhum texto adicional, sem markdown, sem backticks.

{
    "tipo_acao": "tipo da ação (ex: Apelação — Ação de Indenização, Recurso Inominado, etc.)",
    "area_direito": "área (ex: Direito do Consumidor, Direito Civil, Direito Bancário, Direito Imobiliário, Direito Administrativo, Direito Tributário, Direito de Família, Direito Empresarial)",
    "tese_principal": "tese jurídica central (ex: Responsabilidade civil objetiva por falha na prestação de serviço)",
    "tese_secundaria": "segunda tese, se houver (ou null)",
    "resultado": "exatamente uma das opções: provido | parcialmente provido | não provido | não conhecido | prejudicado",
    "resultado_detalhado": "o que foi decidido em 1-2 frases objetivas",
    "autor_nome": "nome do autor/apelante (ou 'Não identificado')",
    "autor_tipo": "Pessoa Física | Consumidor | Pessoa Jurídica | Ente Público | Associação | Condomínio",
    "reu_nome": "nome do réu/apelado (ou 'Não identificado')",
    "reu_tipo": "Banco | Seguradora | Plano de Saúde | Construtora | Concessionária | Ente Público Municipal | Ente Público Estadual | Pessoa Física | Pessoa Jurídica | Operadora de Telecomunicações | Incorporadora",
    "valor_causa": null,
    "valor_condenacao": null,
    "dano_moral_valor": null,
    "fundamentacao_legal": ["Art. 14 CDC", "Art. 927 CC"],
    "precedentes_citados": ["Súmula 297 STJ", "Tema 1069 STF"],
    "palavras_chave": ["5 a 10 palavras-chave relevantes"],
    "resumo_ia": "resumo objetivo em 3-5 frases",
    "observacoes_ia": "observação relevante (ou null)",
    "ia_modelo": "claude-sonnet-4-6"
}

REGRAS:
1. Valores monetários: float sem símbolo (ex: 15000.00) ou null
2. Listas: [] se vazio
3. Não invente — use apenas o que consta no texto
4. resultado: use EXATAMENTE uma das 5 opções listadas"""

USER_PROMPT = """Analise esta decisão do TJ-SP e retorne o JSON estruturado.

METADADOS ESAJ:
- Classe: {classe_processual}
- Assunto: {assunto_esaj}
- Órgão Julgador: {orgao_julgador}
- Relator: {relator}

EMENTA:
{ementa}

INTEIRO TEOR (trecho):
{texto_extraido}

JSON:"""


def _limpar_json(texto: str) -> str:
    """Remove artefatos markdown e retorna apenas o JSON."""
    texto = texto.strip()
    # Remove blocos ```json ... ``` ou ``` ... ```
    if texto.startswith('```'):
        linhas = texto.splitlines()
        # Remove primeira e última linha se são fence
        inicio = 1 if linhas[0].startswith('```') else 0
        fim = len(linhas) - 1 if linhas[-1].strip() == '```' else len(linhas)
        texto = '\n'.join(linhas[inicio:fim])
    return texto.strip()


class AIClassifier:
    """Classifica decisões judiciais usando a API do Claude."""

    def __init__(self, config: dict = None):
        self.config  = config or {}
        api_key = self.config.get('api_key') or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError(
                "Chave Anthropic não configurada. "
                "Defina em config.yaml (anthropic.api_key) ou ANTHROPIC_API_KEY."
            )
        self.client     = anthropic.Anthropic(api_key=api_key)
        self.model      = self.config.get('model', 'claude-sonnet-4-6')
        self.max_tokens = self.config.get('max_tokens', 4096)
        self.db         = JurisprudenciaDB(self.config.get('db_path', 'data/jurisprudencia.db'))

    def classificar(self, decisao: dict, tentativas: int = 2) -> dict | None:
        """
        Classifica uma decisão. Tenta até `tentativas` vezes em caso de JSON inválido.
        """
        ementa        = decisao.get('ementa') or ''
        texto         = (decisao.get('texto_extraido') or '')[:8000]

        if not ementa and not texto:
            logger.warning(f"Sem conteúdo para classificar: {decisao.get('numero_processo')}")
            return None

        prompt = USER_PROMPT.format(
            classe_processual = decisao.get('classe_processual') or 'N/D',
            assunto_esaj      = decisao.get('assunto_esaj')      or 'N/D',
            orgao_julgador    = decisao.get('orgao_julgador')     or 'N/D',
            relator           = decisao.get('relator')            or 'N/D',
            ementa            = ementa or 'N/D',
            texto_extraido    = texto  or 'N/D',
        )

        for tentativa in range(1, tentativas + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                raw = resp.content[0].text
                classificacao = json.loads(_limpar_json(raw))
                classificacao['ia_modelo'] = self.model
                return classificacao

            except json.JSONDecodeError as exc:
                logger.warning(
                    f"JSON inválido (tentativa {tentativa}/{tentativas}): {exc} "
                    f"— processo {decisao.get('numero_processo')}"
                )
                if tentativa == tentativas:
                    logger.error(f"Descartando após {tentativas} tentativas.")
                    return None
                time.sleep(2)

            except anthropic.RateLimitError:
                logger.warning("Rate limit — aguardando 60 s…")
                time.sleep(60)
                return self.classificar(decisao, tentativas=1)

            except anthropic.APIError as exc:
                logger.error(f"Erro API Anthropic: {exc}")
                raise

        return None

    def processar_pendentes(self, limit: int = 50, delay: float = 1.0) -> dict:
        """
        Processa em lote todas as decisões pendentes de classificação.
        """
        pendentes = self.db.pendentes_ia(limit)
        logger.info(f"Pendentes para classificação: {len(pendentes)}")
        stats = {'total': len(pendentes), 'sucesso': 0, 'erro': 0}

        for i, decisao in enumerate(pendentes):
            logger.info(f"[{i+1}/{len(pendentes)}] {decisao['numero_processo']}")
            try:
                cl = self.classificar(decisao)
                if cl:
                    self.db.atualizar_classificacao_ia(decisao['numero_processo'], cl)
                    stats['sucesso'] += 1
                    logger.info(
                        f"  ✓ {cl.get('area_direito')} | "
                        f"{cl.get('tese_principal')} | {cl.get('resultado')}"
                    )
                else:
                    stats['erro'] += 1
                    self.db.registrar_erro(
                        'classificacao_ia', 'Retornou None',
                        numero_processo=decisao['numero_processo'],
                        decisao_id=decisao['id']
                    )
            except anthropic.RateLimitError:
                logger.warning("Rate limit — 60 s")
                time.sleep(60)
                stats['erro'] += 1
            except Exception as exc:
                logger.error(f"Erro: {exc}")
                self.db.registrar_erro(
                    'classificacao_ia', str(exc),
                    numero_processo=decisao['numero_processo'],
                    decisao_id=decisao['id']
                )
                stats['erro'] += 1

            if delay and i < len(pendentes) - 1:
                time.sleep(delay)

        logger.info(f"Classificação concluída: {stats}")
        return stats


def main():
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/classifier.log', encoding='utf-8'),
        ]
    )
    parser = argparse.ArgumentParser(description='Classificador IA — JurisIntel')
    parser.add_argument('--pendentes', action='store_true')
    parser.add_argument('--batch',     '-b', type=int,   default=50)
    parser.add_argument('--delay',     '-d', type=float, default=1.0)
    args = parser.parse_args()

    config = {}
    if os.path.exists('config/config.yaml'):
        import yaml
        with open('config/config.yaml') as f:
            config = (yaml.safe_load(f) or {}).get('anthropic', {})

    if args.pendentes:
        cl = AIClassifier(config)
        r = cl.processar_pendentes(limit=args.batch, delay=args.delay)
        print(f"\nClassificação: {r}")


if __name__ == '__main__':
    main()
