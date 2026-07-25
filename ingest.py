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
import sqlite3
import sys
import time
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


def ingest_paths(conn: sqlite3.Connection, paths: list[Path], force: bool = False) -> int:
    """Ingere arquivos locais e devolve quantas fontes foram atualizadas."""
    ingested = 0
    for path in paths:
        print(f"\n▶ {path.name}")
        try:
            source = extract.load(path)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ erro ao ler: {e}")
            continue

        if not force and dbmod.source_exists(conn, source.sha256):
            print("  • já ingerido (use --force para reprocessar); pulando")
            continue

        print(f"  páginas com texto: {source.page_count}")
        chunks = chunk_source(source)
        lex = build_lexicon(source)
        rituais = sum(1 for e in lex if e.category == "ritual")
        result = dbmod.ingest_source(conn, source, chunks, lex)
        print(f"  chunks: {result['chunks']}  |  léxico: {result['lexicon']} "
              f"(rituais detectados: {rituais})")
        ingested += 1
    return ingested


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestão de livros de Ordem Paranormal")
    ap.add_argument("inputs", nargs="*", help="arquivos ou pastas")
    ap.add_argument("--db", default="ordem.db", help="caminho do banco (default: ordem.db)")
    ap.add_argument("--force", action="store_true", help="reprocessa fontes já ingeridas")
    ap.add_argument("--drive-folder", help="ID ou URL de uma pasta privada do Google Drive")
    ap.add_argument("--drive-credentials", default="credentials.json",
                    help="JSON do cliente OAuth (default: credentials.json)")
    ap.add_argument("--drive-token", default=".ordem-drive/token.json",
                    help="cache local do login OAuth")
    ap.add_argument("--drive-cache", default=".ordem-drive/books",
                    help="diretório privado para os downloads")
    ap.add_argument("--drive-interval", type=int, default=300, metavar="SEGUNDOS",
                    help="intervalo da sincronização; 0 executa uma vez (default: 300)")
    args = ap.parse_args()

    paths = collect_paths(args.inputs)
    if not paths and not args.drive_folder:
        print("Nenhum arquivo suportado encontrado.")
        return 1
    if args.drive_interval < 0:
        ap.error("--drive-interval deve ser maior ou igual a zero")

    conn = dbmod.connect(args.db)
    ingest_paths(conn, paths, force=args.force)

    if args.drive_folder:
        from ordem.drive import DriveSetupError, DriveSync

        sync = DriveSync(
            args.drive_folder,
            cache_dir=args.drive_cache,
            credentials_path=args.drive_credentials,
            token_path=args.drive_token,
        )
        ingest_paths(conn, sync.cached_paths(), force=args.force)
        while True:
            try:
                downloaded = sync.sync_once()
                if downloaded:
                    print(f"\nDrive: {len(downloaded)} arquivo(s) novo(s) ou alterado(s)")
                    ingest_paths(conn, downloaded, force=args.force)
                else:
                    print("\nDrive: nenhuma alteração")
            except DriveSetupError as exc:
                print(f"Drive: {exc}")
                conn.close()
                return 2
            except Exception as exc:  # noqa: BLE001
                print(f"Drive: falha ao sincronizar: {exc}")

            if args.drive_interval == 0:
                break
            print(f"Drive: nova verificação em {args.drive_interval}s (Ctrl+C para parar)")
            try:
                time.sleep(args.drive_interval)
            except KeyboardInterrupt:
                print("\nSincronização encerrada.")
                break

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
