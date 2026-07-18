#!/usr/bin/env python3
"""Suíte de testes do detector de mecânicas.

Cobre: casos positivos variados (5 elementos, círculos, perícias, condições,
recursos), robustez a ruído de STT, conteúdo homebrew, casos negativos
(falso-positivo) e cobertura de todos os rituais.

Uso: python tests/test_detection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ordem import db as dbmod
from ordem.detect import Detector

GREEN, RED, DIM, RESET = "\033[92m", "\033[91m", "\033[2m", "\033[0m"


def terms_of(det: Detector, text: str) -> set[str]:
    return {d.term for d in det.detect(text)}


# (frase, {termos que DEVEM aparecer})
POSITIVOS = [
    # --- Rituais dos 5 elementos, círculos variados ---
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
    # --- Perícias ---
    ("faz um teste de Investigação na cena do crime", {"Investigação"}),
    ("rola Atletismo pra escalar o muro", {"Atletismo"}),
    ("um teste de Diplomacia pra convencer o delegado", {"Diplomacia"}),
    ("usa Medicina pra estabilizar o ferido", {"Medicina"}),
    ("teste de Percepção pra notar a emboscada", {"Percepção"}),
    # --- Condições ---
    ("o personagem fica atordoado por uma rodada", {"Atordoado"}),
    ("você fica caído e desprevenido", {"Caído", "Desprevenido"}),
    ("o alvo fica cego e não enxerga nada", {"Cego"}),
    ("ele está sangrando e perde vida por rodada", {"Sangrando"}),
    # --- Recursos e atributos ---
    ("gasta 3 PE e recupera PV com o descanso", {"PE", "PV"}),
    ("perde 5 de sanidade ao ver a criatura", {"SAN"}),
    ("seu NEX está em 25 por cento", {"NEX"}),
    ("faz um teste de Força pra arrombar a porta", {"Força"}),
    ("usa o Intelecto pra resolver o enigma", {"Intelecto"}),
    # --- Múltiplas mecânicas numa fala longa ---
    ("o ocultista gasta 2 PE, conjura Eletrocussão e o alvo fica atordoado",
     {"PE", "Eletrocussão", "Atordoado"}),
    ("faz Vontade pra resistir ao Medo ou fica apavorado perdendo sanidade",
     {"Vontade", "Apavorado", "SAN"}),
]

# ruído típico de transcrição de voz: acentos faltando, erros fonéticos leves
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

# frases SEM mecânica — não devem gerar detecções
NEGATIVOS = [
    "então vocês entram na sala escura e sentem um cheiro estranho",
    "o mestre pergunta o que vocês querem fazer agora",
    "vou pegar um café rapidinho, já volto pra mesa",
    "a porta range quando você a empurra devagar",
    "faz muito tempo que não jogamos essa campanha",
]


# termos ambíguos (palavras comuns) COM gatilho de jogo — devem detectar
AMBIGUOS_COM_GATILHO = [
    ("faz um teste de Luta", {"Luta"}),
    ("rola um teste de Vontade", {"Vontade"}),
    ("perde 5 pontos de vida", {"PV"}),
    ("faz um teste de Crime pra arrombar o cofre", {"Crime"}),
    ("teste de Força pra levantar o portão", {"Força"}),
    ("um teste de Artes pra tocar violino", {"Artes"}),
]

# termos ambíguos SEM gatilho (conversa normal) — NÃO devem detectar
AMBIGUOS_SEM_GATILHO = [
    "a luta na rua foi violenta",
    "ele cometeu um crime terrível",
    "as artes visuais me interessam muito",
    "tenho vontade de ir embora daqui",
    "a religião dele é muito importante",
    "ela levava uma vida difícil na cidade",
]


# poderes homebrew (extraídos do .txt da campanha)
HOMEBREW = [
    ("ativo Saber é Poder e gasto 2 PE nesse teste", {"Saber é Poder"}),
    ("meu Companheiro Animal evolui em 50 por cento", {"Companheiro Animal"}),
    ("uso Conhecimento Oculto pra identificar a criatura", {"Conhecimento Oculto"}),
    ("ativo minha Mutação e ganho resistência a dano", {"Mutação"}),
]


# erros fortes de STT: palavras partidas e distorção pesada
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

# negativos difíceis: palavras que se PARECEM com mecânicas mas não são
NEG_DIFICIL = [
    "ele tinha conhecimento do assunto",
    "que luz linda no céu",
    "ela tem muita presença de palco",
    "ele sentiu muito medo naquela hora",
    "o sangue escorria pelo chão",
    "a morte rondava a cidade inteira",
    "a energia da sala parecia estranha",
]


# fonte .docx: elemento homebrew "Profundezas", poderes paranormais e
# referência por seção (sem número de página real)
DOCX_FONTE = [
    ("ela conjura Abyssum Gate e abre uma cratera no chão", {"Abyssum Gate"}),
    ("uso Sentidos Apurados pra enxergar no escuro", {"Sentidos Apurados"}),
    ("ativo Antecipar e bloqueio o ataque à distância", {"Antecipar"}),
    ("conjura Túmulo Pelágico contra o grupo", {"Túmulo Pelágico"}),
]


# conteúdo dos pacotes oficiais Arquivos Secretos
ARQUIVOS_SECRETOS = [
    ("conjuro Hesitação Forçada no capanga", {"Hesitação Forçada"}),
    ("ela conjura Labirinto Mental no cultista", {"Labirinto Mental"}),
    ("usa Mapa Sanguíneo pra rastrear o alvo", {"Mapa Sanguíneo"}),
    ("o personagem fica trêmulo de pânico", {"Trêmulo"}),
    ("ativo Grilhões de Lodo no corredor", {"Grilhões de Lodo"}),
    ("uso Escudo Espiral Temporal na munição", {"Escudo Espiral Temporal"}),
]

# combos falados: ritual/poder + versão (Discente/Verdadeiro/Afinidade)
# formato: (frase, termo esperado, tier esperado)
COMBOS_TIER = [
    ("conjura Eletrocussão Verdadeira no grupo", "Eletrocussão", "Verdadeiro"),
    ("uso Hesitação Forçada Discente no capanga", "Hesitação Forçada", "Discente"),
    ("ativo Grilhões de Lodo com afinidade", "Grilhões de Lodo", "Afinidade"),
    ("lança Tecer Ilusão no verdadeiro", "Tecer Ilusão", "Verdadeiro"),
    ("conjura Eletrocussão simples", "Eletrocussão", None),   # sem tier
]


def run_combos(det: Detector) -> tuple[int, int]:
    print("\nCOMBOS DE VERSÃO (Discente/Verdadeiro/Afinidade)")
    ok = 0
    for text, term, tier in COMBOS_TIER:
        found = {d.term: d for d in det.detect(text)}
        d = found.get(term)
        got = d.tier if d else "(não detectado)"
        passed = d is not None and d.tier == tier and \
            (tier is None or bool(d.tier_summary))
        if passed:
            ok += 1
            label = tier or "sem versão"
            print(f"  {GREEN}✓{RESET} {text[:46]:46s} → {term} [{label}]")
        else:
            print(f"  {RED}✗{RESET} {text[:46]:46s} "
                  f"{RED}esperado tier={tier}, obtido={got}{RESET}")
    print(f"  → {ok}/{len(COMBOS_TIER)}")
    return ok, len(COMBOS_TIER)


def run_group(det: Detector, name: str, cases: list) -> tuple[int, int]:
    print(f"\n{name}")
    ok = 0
    for text, expected in cases:
        found = terms_of(det, text)
        missing = expected - found
        if not missing:
            ok += 1
            print(f"  {GREEN}✓{RESET} {text[:52]:52s} → {', '.join(sorted(expected))}")
        else:
            print(f"  {RED}✗{RESET} {text[:52]:52s} "
                  f"{RED}faltou: {', '.join(sorted(missing))}{RESET} "
                  f"{DIM}(achou: {', '.join(sorted(found)) or '—'}){RESET}")
    print(f"  → {ok}/{len(cases)}")
    return ok, len(cases)


def run_negativos(det: Detector) -> tuple[int, int]:
    print("\nCASOS NEGATIVOS (não deve detectar nada)")
    ok = 0
    for text in NEGATIVOS:
        found = terms_of(det, text)
        if not found:
            ok += 1
            print(f"  {GREEN}✓{RESET} {text[:60]}")
        else:
            print(f"  {RED}✗{RESET} {text[:52]:52s} "
                  f"{RED}falso-positivo: {', '.join(sorted(found))}{RESET}")
    print(f"  → {ok}/{len(NEGATIVOS)}")
    return ok, len(NEGATIVOS)


def run_cobertura_rituais(det: Detector, conn) -> tuple[int, int]:
    """Cada ritual deve ser detectado quando 'falado' numa frase."""
    rows = conn.execute("SELECT term FROM lexicon WHERE category='ritual'").fetchall()
    print(f"\nCOBERTURA DE RITUAIS (todos os {len(rows)})")
    ok, falhas = 0, []
    for r in rows:
        nome = r["term"]
        frase = f"o conjurador lança {nome} agora"
        if nome in terms_of(det, frase):
            ok += 1
        else:
            falhas.append(nome)
    print(f"  → {ok}/{len(rows)} rituais detectados")
    if falhas:
        print(f"  {RED}não detectados:{RESET} {', '.join(falhas[:12])}"
              + (" ..." if len(falhas) > 12 else ""))
    return ok, len(rows)


def main() -> int:
    conn = dbmod.connect("ordem.db")
    det = Detector(dbmod.all_lexicon(conn))

    total_ok = total = 0
    for name, cases in [("POSITIVOS", POSITIVOS), ("RUÍDO DE STT", STT_RUIDO),
                        ("STT DIFÍCIL (partidas/distorção)", STT_DIFICIL),
                        ("AMBÍGUOS COM GATILHO", AMBIGUOS_COM_GATILHO),
                        ("PODERES HOMEBREW", HOMEBREW),
                        ("FONTE .DOCX (Profundezas, poderes paranormais)", DOCX_FONTE),
                        ("ARQUIVOS SECRETOS (pacotes oficiais)", ARQUIVOS_SECRETOS)]:
        o, t = run_group(det, name, cases)
        total_ok += o
        total += t

    # grupos que NÃO devem detectar nada
    for label, group in [
        ("AMBÍGUOS SEM GATILHO (conversa normal)", AMBIGUOS_SEM_GATILHO),
        ("NEGATIVOS DIFÍCEIS (parecem mecânica)", NEG_DIFICIL),
    ]:
        print(f"\n{label}")
        o = 0
        for text in group:
            found = terms_of(det, text)
            if not found:
                o += 1
                print(f"  {GREEN}✓{RESET} {text[:60]}")
            else:
                print(f"  {RED}✗{RESET} {text[:40]:40s} "
                      f"{RED}falso-positivo: {', '.join(sorted(found))}{RESET}")
        print(f"  → {o}/{len(group)}")
        total_ok += o
        total += len(group)
    o, t = run_combos(det)
    total_ok += o
    total += t
    o, t = run_cobertura_rituais(det, conn)
    total_ok += o
    total += t

    print("\n" + "=" * 52)
    pct = 100 * total_ok / total
    cor = GREEN if pct >= 95 else RED
    print(f"TOTAL: {cor}{total_ok}/{total} ({pct:.1f}%){RESET}")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
