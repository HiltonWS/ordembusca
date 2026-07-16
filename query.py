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
from ordem.detect import Detector


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
        extra = f" [{d.meta['elemento']} {d.meta['circulo']}]" if d.meta.get("elemento") else ""
        ref = f" — {d.source} p.{d.page}" if d.page else ""
        print(f"● {d.category.upper():9s} {d.term}{extra}  ({d.score}%){ref}")
        if d.summary:
            print(f"    ↳ {d.summary}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
