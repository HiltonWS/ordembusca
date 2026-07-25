from pathlib import Path

import pytest

from ordem.detect import Detector
from ordem.extract import Page, Source
from ordem.lexicon import canonical_entries, extract_poderes, extract_poderes_paranormais
from ordem.pipeline import current_lexicon


def test_condition_does_not_use_incidental_path_mention_as_source():
    source = Source(
        path=Path("trilhas.txt"),
        title="Homebrew",
        sha256="test",
        pages=[Page(1, "A habilidade deixa o alvo fraco.", "Trilhas de Especialista")],
    )

    fraco = next(
        entry for entry in canonical_entries(source)
        if entry.term == "Fraco" and entry.category == "condicao"
    )

    assert fraco.source_filename is None
    assert fraco.page is None
    assert fraco.loc is None


def test_current_lexicon_cleans_legacy_condition_reference(monkeypatch):
    monkeypatch.setattr(
        "ordem.pipeline.dbmod.all_lexicon",
        lambda _conn: [{
            "term": "Fraco", "category": "condicao", "aliases": [], "meta": {},
            "summary": None, "page": 8, "loc": "Trilhas de Especialista",
            "title": "Homebrew", "filename": "trilhas.txt",
        }],
    )

    fraco = next(entry for entry in current_lexicon(None) if entry["term"] == "Fraco")

    assert fraco["title"] is None
    assert fraco["filename"] is None
    assert fraco["page"] is None
    assert fraco["loc"] is None


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
        ("Arma", "Sabre Abissal", "arma"),
        ("Item", "Relógio de Lodo", "item"),
        ("Poder Paranormal", "Pulso Abissal", "poder"),
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


def test_arquivos_secretos_paranormal_power_is_extracted():
    source = Source(
        path=Path("arquivos-secretos.pdf"),
        title="Arquivos Secretos",
        sha256="synthetic",
        pages=[Page(12, "Pulso Entrópico\nPODER PARANORMAL MORTE\nAltera o fluxo temporal.")],
    )

    entries = extract_poderes_paranormais(source)

    assert [(entry.term, entry.category) for entry in entries] == [
        ("Pulso Entrópico", "poder")
    ]
    assert entries[0].meta["elemento"] == "Morte"
    assert entries[0].page == 12


def test_homebrew_weapon_item_and_power_are_detected():
    source = Source(
        path=Path("homebrew.txt"),
        title="Homebrew",
        sha256="synthetic",
        pages=[Page(1, "\n".join([
            "[Arma: Sabre Abissal] - Uma arma das profundezas.",
            "[Item: Relógio de Lodo] - Um item temporal.",
            "[Poder Paranormal: Pulso Abissal] - Um poder de Morte.",
        ]))],
    )
    entries = extract_poderes(source)
    lexicon = [
        {"term": entry.term, "category": entry.category, "aliases": entry.aliases,
         "meta": entry.meta, "summary": entry.summary}
        for entry in entries
    ]

    detections = Detector(lexicon).detect(
        "equipo o Sabre Abissal, uso o Relógio de Lodo e ativo Pulso Abissal"
    )

    assert {(item.term, item.category) for item in detections} == {
        ("Sabre Abissal", "arma"),
        ("Relógio de Lodo", "item"),
        ("Pulso Abissal", "poder"),
    }
