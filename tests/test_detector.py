"""Testes do detector de mecânicas (pytest).

Roda com ou sem os livros: sem ordem.db usa a fixture (tests/fixtures.py);
com ordem.db também valida a cobertura dos rituais extraídos dos livros.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ordem.detect import Detector  # noqa: E402
from tests.fixtures import fixture_lexicon, load_lexicon  # noqa: E402

LEXICON = fixture_lexicon()
DB_LEXICON, FROM_DB = load_lexicon()


@pytest.fixture(scope="session")
def detector() -> Detector:
    return Detector(LEXICON)


def terms_of(det: Detector, text: str) -> set[str]:
    return {d.term for d in det.detect(text)}


# ---------------------------------------------------------------- positivos
POSITIVOS = [
    ("o guerreiro conjura Armadura de Sangue antes da luta", {"Armadura de Sangue"}),
    ("ele usa Arma Atroz pra deixar a lâmina mais mortal", {"Arma Atroz"}),
    ("a ocultista lança Cicatrização pra curar o aliado", {"Cicatrização"}),
    ("conjuro Definhar no inimigo pra enfraquecê-lo", {"Definhar"}),
    ("uso Compreensão Paranormal pra ler aquela inscrição", {"Compreensão Paranormal"}),
    ("ela conjura Tecer Ilusão pra enganar os guardas", {"Tecer Ilusão"}),
    ("solta uma Eletrocussão na poça d'água", {"Eletrocussão"}),
    ("conjura Luz pra iluminar a caverna", {"Luz"}),
    ("o mestre descreve Canalizar o Medo tomando a sala", {"Canalizar o Medo"}),
    ("ela usa Proteção contra Rituais no grupo", {"Proteção contra Rituais"}),
    ("faz um teste de Investigação na cena do crime", {"Investigação"}),
    ("rola Atletismo pra escalar o muro", {"Atletismo"}),
    ("um teste de Diplomacia pra convencer o delegado", {"Diplomacia"}),
    ("usa Medicina pra estabilizar o ferido", {"Medicina"}),
    ("teste de Percepção pra notar a emboscada", {"Percepção"}),
    ("o personagem fica atordoado por uma rodada", {"Atordoado"}),
    ("você fica caído e desprevenido", {"Caído", "Desprevenido"}),
    ("o alvo fica cego e não enxerga nada", {"Cego"}),
    ("ele está sangrando e perde vida por rodada", {"Sangrando"}),
    ("gasta 3 PE e recupera PV com o descanso", {"PE", "PV"}),
    ("perde 5 de sanidade ao ver a criatura", {"SAN"}),
    ("seu NEX está em 25 por cento", {"NEX"}),
    ("faz um teste de Força pra arrombar a porta", {"Força"}),
    ("usa o Intelecto pra resolver o enigma", {"Intelecto"}),
    ("o ocultista gasta 2 PE, conjura Eletrocussão e o alvo fica atordoado",
     {"PE", "Eletrocussão", "Atordoado"}),
    ("faz Vontade pra resistir ao Medo ou fica apavorado perdendo sanidade",
     {"Vontade", "Apavorado", "SAN"}),
]

STT_RUIDO = [
    ("faz um teste de ocultismo", {"Ocultismo"}),
    ("conjura sopro do caos", {"Sopro do Caos"}),
    ("ele fica apavorado", {"Apavorado"}),
    ("rola resistencia de vontade", {"Vontade"}),
    ("presenca do medo atinge todos", {"Presença do Medo"}),
    ("perde pontos de sanidade", {"SAN"}),
    ("teste de furtividade", {"Furtividade"}),
    ("conjura armadura de sangue", {"Armadura de Sangue"}),
]

STT_DIFICIL = [
    ("rola oculto ismo", {"Ocultismo"}),
    ("teste de furti vidade", {"Furtividade"}),
    ("faz investi gação na cena", {"Investigação"}),
    ("solta uma eletro cussão", {"Eletrocussão"}),
    ("conjura sopro do ca os", {"Sopro do Caos"}),
    ("tesse ilusao pra enganar", {"Tecer Ilusão"}),
    ("armadura de sange antes da briga", {"Armadura de Sangue"}),
    ("kanalizar o medo toma a sala", {"Canalizar o Medo"}),
    ("ele fica apavorrado", {"Apavorado"}),
]

AMBIGUOS_COM_GATILHO = [
    ("faz um teste de Luta", {"Luta"}),
    ("rola um teste de Vontade", {"Vontade"}),
    ("perde 5 pontos de vida", {"PV"}),
    ("faz um teste de Crime pra arrombar o cofre", {"Crime"}),
    ("teste de Força pra levantar o portão", {"Força"}),
    ("um teste de Artes pra tocar violino", {"Artes"}),
]

HOMEBREW = [
    ("ativo Saber é Poder e gasto 2 PE nesse teste", {"Saber é Poder"}),
    ("meu Companheiro Animal evolui em 50 por cento", {"Companheiro Animal"}),
    ("uso Conhecimento Oculto pra identificar a criatura", {"Conhecimento Oculto"}),
    ("ativo minha Mutação e ganho resistência a dano", {"Mutação"}),
]

# ------------------------------------------------------------- negativos
AMBIGUOS_SEM_GATILHO = [
    "a luta na rua foi violenta",
    "ele cometeu um crime terrível",
    "as artes visuais me interessam muito",
    "tenho vontade de ir embora daqui",
    "a religião dele é muito importante",
    "ela levava uma vida difícil na cidade",
]

NEG_DIFICIL = [
    "ele tinha conhecimento do assunto",
    "que luz linda no céu",
    "ela tem muita presença de palco",
    "ele sentiu muito medo naquela hora",
    "o sangue escorria pelo chão",
    "a morte rondava a cidade inteira",
    "a energia da sala parecia estranha",
]

NEGATIVOS = [
    "então vocês entram na sala escura e sentem um cheiro estranho",
    "o mestre pergunta o que vocês querem fazer agora",
    "vou pegar um café rapidinho, já volto pra mesa",
    "a porta range quando você a empurra devagar",
    "faz muito tempo que não jogamos essa campanha",
]


# ------------------------------------------------------------------ testes
@pytest.mark.parametrize("text,expected", POSITIVOS)
def test_positivos(detector, text, expected):
    assert expected <= terms_of(detector, text)


@pytest.mark.parametrize("text,expected", STT_RUIDO)
def test_ruido_stt(detector, text, expected):
    assert expected <= terms_of(detector, text)


@pytest.mark.parametrize("text,expected", STT_DIFICIL)
def test_stt_dificil_partidas_e_distorcao(detector, text, expected):
    assert expected <= terms_of(detector, text)


@pytest.mark.parametrize("text,expected", AMBIGUOS_COM_GATILHO)
def test_ambiguos_com_gatilho_detectam(detector, text, expected):
    assert expected <= terms_of(detector, text)


@pytest.mark.parametrize("text,expected", HOMEBREW)
def test_poderes_homebrew(detector, text, expected):
    assert expected <= terms_of(detector, text)


@pytest.mark.parametrize("text", AMBIGUOS_SEM_GATILHO)
def test_ambiguos_sem_gatilho_nao_detectam(detector, text):
    assert terms_of(detector, text) == set()


@pytest.mark.parametrize("text", NEG_DIFICIL)
def test_negativos_dificeis(detector, text):
    assert terms_of(detector, text) == set()


@pytest.mark.parametrize("text", NEGATIVOS)
def test_negativos_simples(detector, text):
    assert terms_of(detector, text) == set()


# --------------------------------------------- cobertura (só com ordem.db)
@pytest.mark.skipif(not FROM_DB, reason="requer ordem.db (livros ingeridos)")
def test_cobertura_todos_os_rituais():
    detector = Detector(DB_LEXICON)
    rituais = [e["term"] for e in DB_LEXICON if e["category"] == "ritual"]
    assert len(rituais) >= 80
    falhas = [n for n in rituais
              if n not in terms_of(detector, f"o conjurador lança {n} agora")]
    assert not falhas, f"rituais não detectados: {falhas}"


# ------------------------------------------------- unidades do matcher
def test_fonetica_pt():
    from ordem.detect import phonetic_pt
    assert phonetic_pt("tecer") == phonetic_pt("tesser")
    assert phonetic_pt("caos") == phonetic_pt("kaos")
    assert phonetic_pt("chave") == phonetic_pt("xave")


def test_siglas_exigem_match_exato(detector):
    # 'pé' normaliza para 'pe' e casa; 'per' não deve casar com PE
    assert "PE" not in terms_of(detector, "ele quebrou o per na corrida")


def test_supressao_substring(detector):
    dets = detector.detect("ele conjura Presença do Medo")
    terms = {d.term for d in dets}
    assert "Presença do Medo" in terms
    assert "Presença" not in terms
