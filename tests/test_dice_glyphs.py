"""Testes da restauração da notação de dados (ícone d20 extraído como 'O')."""
from __future__ import annotations

from ordem.extract import fix_dice_glyphs


def test_dado_apos_digito():
    assert fix_dice_glyphs("Teste 2O+5, crítico 19") == "Teste 2d20+5, crítico 19"
    assert fix_dice_glyphs("Atletismo 3O+10, Tática 4O+10") == \
        "Atletismo 3d20+10, Tática 4d20+10"


def test_dado_sozinho_antes_de_mais():
    assert fix_dice_glyphs("Percepção O+5 | Iniciativa O+5") == \
        "Percepção d20+5 | Iniciativa d20+5"


def test_multiplos_icones_antes_de_mais():
    assert fix_dice_glyphs("manobra derrubar (bônus OO+5)") == \
        "manobra derrubar (bônus 2d20+5)"


def test_penalidade_com_travessao():
    assert fix_dice_glyphs("sofre –O em testes") == "sofre –1d20 em testes"
    assert fix_dice_glyphs("sofre –OO em testes") == "sofre –2d20 em testes"


def test_apos_palavra_chave_sem_bonus():
    assert fix_dice_glyphs("Fortitude O | Reflexos 2O+5") == \
        "Fortitude d20 | Reflexos 2d20+5"


def test_nao_toca_no_artigo():
    for frase in ["O ocultista conjura o ritual", "O Outro Lado observa",
                  "perde 2d8 PV e O item quebra", "Dano 1d8+10 corte"]:
        assert fix_dice_glyphs(frase) == frase
