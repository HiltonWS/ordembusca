"""Extração e limpeza de texto de fontes (PDF, TXT).

Cada fonte vira uma lista de "páginas": (numero_pagina, texto_limpo).
Para TXT (sem paginação real) devolvemos uma única "página" 1.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

# Linhas de marca d'água / rodapé a remover (o email do dono do PDF etc.)
_WATERMARK_PATTERNS = [
    re.compile(r"\bhilton@hiltonws\.com\b", re.I),
    re.compile(r"^\s*Hilton Silva\s*$", re.I),
]


@dataclass
class Page:
    number: int          # 1-indexed
    text: str            # texto limpo
    loc: str | None = None   # rótulo de localização legível (ex: nome da seção
                              # para fontes sem paginação real); None -> usa "p.N"

    @property
    def display_loc(self) -> str:
        return self.loc or f"p.{self.number}"


@dataclass
class Source:
    path: Path
    title: str
    sha256: str
    pages: list[Page]

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _clean_line(line: str) -> str | None:
    """Remove marcas d'água; devolve None se a linha deve ser descartada."""
    for pat in _WATERMARK_PATTERNS:
        if pat.search(line):
            # se a linha é SÓ a marca d'água, descarta; senão limpa o trecho
            stripped = pat.sub("", line).strip()
            if not stripped:
                return None
            line = stripped
    return line


# Hífen de quebra de linha: "prote-\nge" -> "protege"
_HYPHEN_BREAK = re.compile(r"(\w)[\u00ad\-]\n(\w)")
# Caractere soft-hyphen solto
_SOFT_HYPHEN = re.compile(r"\u00ad")


def _clean_page_text(raw: str) -> str:
    lines = []
    for line in raw.split("\n"):
        cleaned = _clean_line(line)
        if cleaned is not None:
            lines.append(cleaned)
    text = "\n".join(lines)
    # junta palavras quebradas por hífen no fim da linha
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _SOFT_HYPHEN.sub("", text)
    # normaliza espaços múltiplos preservando quebras de linha
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf(path: Path) -> Source:
    doc = fitz.open(path)
    pages: list[Page] = []
    for i, page in enumerate(doc):
        raw = page.get_text("text")
        cleaned = _clean_page_text(raw)
        if cleaned:  # descarta páginas vazias (só arte)
            pages.append(Page(number=i + 1, text=cleaned))
    title = _title_from_filename(path)
    return Source(path=path, title=title, sha256=_sha256(path), pages=pages)


def load_txt(path: Path) -> Source:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # normaliza CRLF e caracteres unicode "estilizados" do título/corpo
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _clean_page_text(raw)
    pages = [Page(number=1, text=cleaned)] if cleaned else []
    return Source(path=path, title=_title_from_filename(path),
                  sha256=_sha256(path), pages=pages)


def _normalize_fancy_unicode(s: str) -> str:
    """Converte letras 'matemáticas' estilizadas (𝑯𝒐𝒎𝒆...) em ASCII normal."""
    out = []
    for ch in s:
        decomp = unicodedata.normalize("NFKC", ch)
        out.append(decomp)
    return "".join(out)


def _title_from_filename(path: Path) -> str:
    name = _normalize_fancy_unicode(path.stem)
    name = name.replace("_", " ").strip()
    # remove sufixos de versão comuns: "v1 3", "1 3", "-1"
    name = re.sub(r"\s+v?\d+([ ._]\d+)*(-\d+)?\s*$", "", name).strip()
    return name or path.stem


_TITLE_STYLES = {"Title", "Heading 1"}


def load_docx(path: Path) -> Source:
    """Extrai um .docx preservando as seções reais (estilos Título/Heading 1)
    como 'páginas' lógicas — cada uma vira o rótulo de localização (loc)
    exibido nas referências, já que docx não tem paginação real.
    """
    import docx  # python-docx

    doc = docx.Document(str(path))
    pages: list[Page] = []
    section_title: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf
        text = _clean_page_text("\n".join(buf))
        if text:
            # injeta o título em CAIXA ALTA como 1ª linha: permite que
            # chunk.py detecte a seção real do mesmo jeito que faz com
            # os cabeçalhos em caixa alta dos PDFs.
            head = section_title.upper() if section_title else None
            full = f"{head}\n\n{text}" if head else text
            pages.append(Page(number=len(pages) + 1, text=full,
                              loc=section_title))
        buf = []

    for p in doc.paragraphs:
        style = p.style.name if p.style else ""
        if style in _TITLE_STYLES and p.text.strip():
            flush()
            section_title = p.text.strip()
            continue
        buf.append(p.text)
    flush()

    return Source(path=path, title=_title_from_filename(path),
                  sha256=_sha256(path), pages=pages)


def load(path: str | Path) -> Source:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    if ext in (".txt", ".md"):
        return load_txt(path)
    if ext == ".docx":
        return load_docx(path)
    raise ValueError(f"Extensão não suportada: {ext}")


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_term(s: str) -> str:
    """Normalização para matching: minúsculas, sem acento, espaços colapsados."""
    s = _normalize_fancy_unicode(s)
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
