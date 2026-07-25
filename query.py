#!/usr/bin/env python3
"""Consulta ao banco: detecta mecânicas numa frase e mostra o contexto.

Uso:
    python query.py "faz um teste de Ocultismo e conjura Sopro do Caos"
    python query.py --db ordem.db "seu texto aqui"
    python query.py --search "exposição paranormal"   # só busca full-text
"""
from __future__ import annotations

import argparse
import sys

from ordem import db as dbmod
from ordem.detect import Detector, format_ref, is_explanation_question


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("texto", help="frase (fala) a analisar")
    ap.add_argument("--db", default="ordem.db")
    ap.add_argument("--search", action="store_true",
                    help="apenas busca full-text, sem detecção")
    args = ap.parse_args()

    conn = dbmod.connect(args.db)

    if args.search:
        for r in dbmod.search_fts(conn, args.texto, limit=3):
            print(f"[{r['title']} p.{r['page']}] {r['section'] or ''}")
            print("  " + r["content"].replace("\n", " ")[:300] + "...\n")
        return 0

    det = Detector(dbmod.all_lexicon(conn))
    detections = det.detect(args.texto)
    if not detections:
        print("Nenhuma mecânica reconhecida.")
        return 0

    print(f'Fala: "{args.texto}"\n')
    for d in detections:
        if d.meta.get("elemento"):
            circ = d.meta.get("circulo")
            extra = f" [{d.meta['elemento']}{f' {circ}' if circ else ''}]"
        else:
            extra = ""
        ref = f" — {format_ref(d)}" if d.source else ""
        print(f"● {d.category.upper():9s} {d.term}{extra}  ({d.score}%){ref}")
        if d.summary:
            print(f"    ↳ {d.summary}")
        if d.tier:
            print(f"    ★ {d.tier}: {d.tier_summary}")
        if is_explanation_question(args.texto):
            details = dbmod.explain_term(conn, d.term)
            if details:
                print(f"    Regra ampliada:\n{details}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
