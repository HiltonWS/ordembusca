#!/usr/bin/env python3
"""Ingestão de fontes (PDF/TXT) para o banco local.

Uso:
    python ingest.py arquivo1.pdf arquivo2.pdf ...
    python ingest.py pasta/            # ingere todos os PDFs/TXT da pasta
    python ingest.py --db meu.db arquivo.pdf
    python ingest.py --force arquivo.pdf   # reprocessa mesmo se já existir

Adicionar mais fontes depois é só rodar de novo com os novos arquivos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ordem import db as dbmod
from ordem import extract
from ordem.chunk import chunk_source
from ordem.lexicon import build_lexicon

SUPPORTED = {".pdf", ".txt", ".md", ".docx"}


def collect_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            paths += [q for q in sorted(p.iterdir())
                      if q.suffix.lower() in SUPPORTED]
        elif p.suffix.lower() in SUPPORTED:
            paths.append(p)
        else:
            print(f"  ignorado (extensão não suportada): {p.name}")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestão de livros de Ordem Paranormal")
    ap.add_argument("inputs", nargs="+", help="arquivos ou pastas")
    ap.add_argument("--db", default="ordem.db", help="caminho do banco (default: ordem.db)")
    ap.add_argument("--force", action="store_true", help="reprocessa fontes já ingeridas")
    args = ap.parse_args()

    paths = collect_paths(args.inputs)
    if not paths:
        print("Nenhum arquivo suportado encontrado.")
        return 1

    conn = dbmod.connect(args.db)
    for path in paths:
        print(f"\n▶ {path.name}")
        try:
            source = extract.load(path)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ erro ao ler: {e}")
            continue

        if not args.force and dbmod.source_exists(conn, source.sha256):
            print("  • já ingerido (use --force para reprocessar); pulando")
            continue

        print(f"  páginas com texto: {source.page_count}")
        chunks = chunk_source(source)
        lex = build_lexicon(source)
        rituais = sum(1 for e in lex if e.category == "ritual")
        result = dbmod.ingest_source(conn, source, chunks, lex)
        print(f"  chunks: {result['chunks']}  |  léxico: {result['lexicon']} "
              f"(rituais detectados: {rituais})")

    print("\n" + "=" * 48)
    s = dbmod.stats(conn)
    print(f"BANCO: {args.db}")
    print(f"  fontes : {s['sources']}")
    print(f"  chunks : {s['chunks']}")
    print(f"  léxico : {s['lexicon']}")
    for cat, n in s["por_categoria"].items():
        print(f"      - {cat:10s}: {n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
