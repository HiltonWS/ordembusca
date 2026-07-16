"""Fixture de léxico para os testes rodarem SEM os livros (CI-safe).

Os livros de Ordem Paranormal são material com direitos autorais e não
são versionados no repositório. Esta fixture combina:
  - termos canônicos do sistema (perícias, condições, recursos, atributos),
    que já vivem no código em ordem/lexicon.py
  - entradas sintéticas de rituais e poderes com os MESMOS nomes usados
    nos casos de teste (nomes de mecânicas não são texto do livro)

Se um ordem.db real existir na raiz, os testes usam-no; senão, usam esta
fixture — o comportamento do Detector é o mesmo.
"""
from __future__ import annotations

from ordem.lexicon import LexEntry, canonical_entries

# rituais reais citados nos testes: (nome, elemento, círculo)
_RITUAIS = [
    ("Armadura de Sangue", "Sangue", 1),
    ("Arma Atroz", "Sangue", 1),
    ("Cicatrização", "Morte", 1),
    ("Definhar", "Morte", 1),
    ("Compreensão Paranormal", "Conhecimento", 1),
    ("Tecer Ilusão", "Conhecimento", 1),
    ("Eletrocussão", "Energia", 1),
    ("Luz", "Energia", 1),
    ("Sopro do Caos", "Energia", 2),
    ("Canalizar o Medo", "Medo", 4),
    ("Presença do Medo", "Medo", 4),
    ("Proteção contra Rituais", "Medo", 2),
]

# poderes homebrew citados nos testes
_PODERES = [
    ("Saber é Poder", "Quando faz um teste usando Intelecto ou Presença, "
     "pode gastar 2 PE para receber +5."),
    ("Companheiro Animal", "Bônus do companheiro se ativam em marcos de NEX."),
    ("Conhecimento Oculto", "Bônus ao identificar criaturas paranormais."),
    ("Mutação", "Resistência a dano 5 e +2 em uma perícia física."),
]


def _entries_to_dicts(entries: list[LexEntry]) -> list[dict]:
    return [
        {
            "term": e.term, "category": e.category, "aliases": e.aliases,
            "meta": e.meta, "summary": e.summary, "page": e.page,
            "title": None, "filename": None,
        }
        for e in entries
    ]


def fixture_lexicon() -> list[dict]:
    entries = canonical_entries(None)   # sem fonte: só termos canônicos
    for nome, elemento, circulo in _RITUAIS:
        entries.append(LexEntry(
            term=nome, category="ritual",
            meta={"elemento": elemento, "circulo": circulo},
        ))
    for nome, desc in _PODERES:
        entries.append(LexEntry(term=nome, category="poder", summary=desc))
    return _entries_to_dicts(entries)


def load_lexicon() -> tuple[list[dict], bool]:
    """(léxico, veio_do_banco). Usa ordem.db se existir; senão a fixture."""
    from pathlib import Path

    db_path = Path(__file__).resolve().parent.parent / "ordem.db"
    if db_path.exists():
        from ordem import db as dbmod
        conn = dbmod.connect(db_path)
        return dbmod.all_lexicon(conn), True
    return fixture_lexicon(), False
