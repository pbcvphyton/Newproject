"""
JurisIntel — Extração de texto de PDFs de acórdãos.

Pipeline:
  1. pdfplumber  — PDFs com texto nativo (rápido, preciso)
  2. Tesseract   — PDFs escaneados / imagem (fallback OCR)

Limpeza pós-extração:
  - Remove cabeçalhos/rodapés repetitivos do TJ-SP
  - Normaliza espaços e quebras de linha
  - Descarta páginas em branco
"""

import os
import re
import logging
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import JurisprudenciaDB

logger = logging.getLogger(__name__)

# Padrões a remover (cabeçalhos/rodapés comuns do TJ-SP)
_LIXO_TJSP = re.compile(
    r'(Tribunal de Justiça do Estado de São Paulo|'
    r'PODER JUDICIÁRIO|'
    r'Fls\.\s*\d+|'
    r'ACÓRDÃO\s*-\s*REGISTRO\s*Nº|'
    r'Este documento é cópia do original)',
    re.IGNORECASE
)


def _limpar_texto(texto: str) -> str:
    """Remove artefatos, normaliza espaçamento e linhas em branco excessivas."""
    linhas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if _LIXO_TJSP.search(linha) and len(linha) < 120:
            continue
        linhas.append(linha)
    texto = '\n'.join(linhas)
    # Colapsar 3+ quebras de linha em 2
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def extrair_texto_pdf(pdf_path: str) -> str | None:
    """
    Extrai texto de um PDF.
    Usa pdfplumber; se o resultado for muito curto (< 100 chars),
    tenta OCR com Tesseract.
    """
    if not os.path.exists(pdf_path):
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        return None

    texto = ''
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if page_text:
                    texto += page_text + '\n'
    except Exception as exc:
        logger.error(f"pdfplumber falhou em {pdf_path}: {exc}")
        return None

    texto = _limpar_texto(texto)

    if len(texto) < 100:
        logger.info(f"Texto curto ({len(texto)} chars), tentando OCR: {pdf_path}")
        ocr = _extrair_ocr(pdf_path)
        if ocr and len(ocr) > len(texto):
            texto = ocr

    return texto or None


def _extrair_ocr(pdf_path: str) -> str | None:
    """Fallback OCR via pdf2image + pytesseract (Português)."""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(pdf_path, dpi=300, fmt='jpeg')
        partes = []
        for img in images:
            t = pytesseract.image_to_string(img, lang='por', config='--psm 1')
            if t.strip():
                partes.append(t)
        return _limpar_texto('\n'.join(partes)) or None

    except ImportError:
        logger.warning("pdf2image/pytesseract não instalado — OCR indisponível.")
        return None
    except Exception as exc:
        logger.error(f"OCR falhou em {pdf_path}: {exc}")
        return None


def processar_pendentes(db_path: str = 'data/jurisprudencia.db', limit: int = 100) -> dict:
    """Processa todos os PDFs com texto pendente de extração."""
    db = JurisprudenciaDB(db_path)
    pendentes = db.pendentes_extracao(limit)
    logger.info(f"PDFs pendentes para extração: {len(pendentes)}")

    stats = {'total': len(pendentes), 'sucesso': 0, 'erro': 0}

    for item in pendentes:
        try:
            texto = extrair_texto_pdf(item['pdf_path'])
            if texto:
                db.atualizar_texto(item['numero_processo'], texto)
                stats['sucesso'] += 1
                logger.debug(f"Extraído: {item['numero_processo']} ({len(texto)} chars)")
            else:
                stats['erro'] += 1
                db.registrar_erro('extracao_texto', 'Texto vazio',
                                  numero_processo=item['numero_processo'],
                                  decisao_id=item['id'])
        except Exception as exc:
            logger.error(f"Erro em {item['numero_processo']}: {exc}")
            db.registrar_erro('extracao_texto', str(exc),
                              numero_processo=item['numero_processo'],
                              decisao_id=item['id'])
            stats['erro'] += 1

    logger.info(f"Extração concluída: {stats}")
    return stats


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    processar_pendentes()
