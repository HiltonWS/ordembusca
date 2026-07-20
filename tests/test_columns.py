"""Testes da leitura de PDF com consciência de colunas.

Usa uma "página" sintética (stub com get_text('blocks') e rect) para
garantir que: a coluna esquerda sai inteira antes da direita, títulos de
largura total segmentam a página, e números de página são descartados.
"""
from __future__ import annotations

from ordem.extract import _page_text_columns


class _Rect:
    def __init__(self, w):
        self.width = w


class _FakePage:
    def __init__(self, blocks, width=600):
        self._blocks = blocks
        self.rect = _Rect(width)

    def get_text(self, kind):
        assert kind == "blocks"
        return self._blocks


def _b(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text, 0, 0)


def test_coluna_esquerda_inteira_antes_da_direita():
    page = _FakePage([
        _b(320, 50, 560, 70, "DIREITA-1\n"),
        _b(40, 50, 280, 70, "ESQUERDA-1\n"),
        _b(40, 300, 280, 320, "ESQUERDA-2\n"),
        _b(320, 100, 560, 120, "DIREITA-2\n"),
    ])
    out = _page_text_columns(page)
    assert out.index("ESQUERDA-1") < out.index("ESQUERDA-2") \
        < out.index("DIREITA-1") < out.index("DIREITA-2")


def test_titulo_largura_total_segmenta():
    page = _FakePage([
        _b(40, 50, 280, 70, "topo-esq\n"),
        _b(320, 50, 560, 70, "topo-dir\n"),
        _b(40, 200, 560, 230, "TITULO CENTRAL\n"),
        _b(40, 300, 280, 320, "baixo-esq\n"),
        _b(320, 300, 560, 320, "baixo-dir\n"),
    ])
    out = _page_text_columns(page)
    # tudo do topo vem antes do título; tudo de baixo, depois
    assert out.index("topo-esq") < out.index("topo-dir") \
        < out.index("TITULO CENTRAL") \
        < out.index("baixo-esq") < out.index("baixo-dir")


def test_numero_de_pagina_descartado():
    page = _FakePage([
        _b(540, 740, 560, 755, "131\n"),
        _b(40, 50, 280, 70, "conteudo\n"),
    ])
    out = _page_text_columns(page)
    assert "131" not in out
    assert "conteudo" in out


def test_pagina_vazia():
    assert _page_text_columns(_FakePage([])) == ""
