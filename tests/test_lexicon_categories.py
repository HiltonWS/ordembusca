from pathlib import Path

import pytest

from ordem.extract import Page, Source
from ordem.lexicon import extract_poderes


@pytest.mark.parametrize(
    "label,name,category",
    [
        ("Característica Única", "Maré Viva", "caracteristica"),
        ("Efeito", "Eco Sangrento", "efeito"),
        ("Classe", "Investigador", "classe"),
        ("Sobrevivente", "Improvisador", "sobrevivente"),
        ("Alteração de NEX", "Despertar Tardio", "nex"),
        ("Perseguição", "Fuga no Porto", "perseguicao"),
        ("Combate", "Maré Violenta", "combate"),
        ("Habilidade de Máscara", "Face do Carrasco", "mascara"),
        ("Armadura", "Couraça Abissal", "armadura"),
        ("Trilha", "Navegador do Oculto", "trilha"),
        ("Vestimenta", "Casaco de Lodo", "vestimenta"),
        ("Acessório", "Lente Espectral", "acessorio"),
        ("Sinergia", "Maré e Tormenta", "sinergia"),
    ],
)
def test_explicit_homebrew_category_is_extracted(label, name, category):
    source = Source(
        path=Path("homebrew.txt"),
        title="Homebrew",
        sha256="synthetic",
        pages=[Page(1, f"[{label}: {name}] - Descrição da mecânica.", "Mecânicas")],
    )

    entries = extract_poderes(source)

    assert [(entry.term, entry.category) for entry in entries] == [(name, category)]
    assert entries[0].summary == "Descrição da mecânica."
    assert entries[0].loc == "Mecânicas"


def test_unlabeled_homebrew_entry_remains_power():
    source = Source(
        path=Path("homebrew.txt"),
        title="Homebrew",
        sha256="synthetic",
        pages=[Page(1, "[Saber é Poder] - Recebe +5 no teste.")],
    )

    entries = extract_poderes(source)

    assert [(entry.term, entry.category) for entry in entries] == [("Saber é Poder", "poder")]
