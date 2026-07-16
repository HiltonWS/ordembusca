"""Divisão do texto em chunks pesquisáveis.

Cada chunk carrega: fonte, página, seção detectada (último cabeçalho em
CAIXA ALTA) e o texto. Chunks são o contexto exibido quando uma mecânica
é reconhecida na fala.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Source


@dataclass
class Chunk:
    source_filename: str
    page: int
    section: str | None
    kind: str          # 'text' por enquanto (rituais entram no léxico)
    content: str


_HEADER = re.compile(r"^[A-ZÀ-Ú][A-ZÀ-Ú\s]{2,40}$")
_TARGET = 700          # tamanho-alvo do chunk em caracteres
_MAX = 1100


def _is_header(line: str) -> bool:
    line = line.strip()
    if not _HEADER.match(line):
        return False
    # evita capturar coisas como "MEDO 4" (cabeçalho de ritual)
    return not re.search(r"\d", line)


def _paragraphs(text: str) -> list[str]:
    # agrupa por linhas em branco; junta linhas soltas dentro do parágrafo
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.strip():
            cur.append(line.strip())
        elif cur:
            blocks.append(" ".join(cur))
            cur = []
    if cur:
        blocks.append(" ".join(cur))
    return blocks


def chunk_source(source: Source) -> list[Chunk]:
    chunks: list[Chunk] = []
    section: str | None = None
    for page in source.pages:
        buf: list[str] = []
        buf_len = 0

        def flush():
            nonlocal buf, buf_len
            if buf:
                content = "\n".join(buf).strip()
                if len(content) >= 40:
                    chunks.append(Chunk(source.filename, page.number,
                                        section, "text", content))
                buf, buf_len = [], 0

        for para in _paragraphs(page.text):
            if _is_header(para):
                flush()
                section = para.title()
                continue
            # parágrafo grande sozinho vira chunk próprio
            if len(para) > _MAX:
                flush()
                chunks.append(Chunk(source.filename, page.number,
                                    section, "text", para))
                continue
            if buf_len + len(para) > _TARGET and buf:
                flush()
            buf.append(para)
            buf_len += len(para) + 1
        flush()
    return chunks
