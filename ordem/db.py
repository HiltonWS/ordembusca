"""Banco de dados local: SQLite + FTS5.

Tabelas:
  sources  — cada arquivo ingerido (dedup por sha256)
  chunks   — blocos de texto com página/seção
  chunks_fts — índice full-text (unicode61, remove_diacritics) sobre chunks
  lexicon  — termos de mecânicas (rituais, perícias, condições, recursos)

FTS5 com remove_diacritics=2 casa "pericia"~"perícia", ótimo para texto
vindo de transcrição de voz.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .chunk import Chunk
from .extract import Source, normalize_term
from .lexicon import LexEntry

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY,
    filename     TEXT UNIQUE NOT NULL,
    title        TEXT,
    sha256       TEXT NOT NULL,
    pages        INTEGER,
    ingested_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    page       INTEGER,
    section    TEXT,
    kind       TEXT,
    content    TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, section,
    content='chunks', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content, section)
    VALUES (new.id, new.content, new.section);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, section)
    VALUES('delete', old.id, old.content, old.section);
END;

CREATE TABLE IF NOT EXISTS lexicon (
    id         INTEGER PRIMARY KEY,
    term       TEXT NOT NULL,
    norm       TEXT NOT NULL,
    category   TEXT NOT NULL,
    aliases    TEXT,              -- JSON array
    meta       TEXT,              -- JSON object
    summary    TEXT,              -- resumo curto da regra
    loc        TEXT,              -- rótulo de localização (seção, se sem página real)
    source_id  INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    page       INTEGER,
    UNIQUE(norm, category)
);
CREATE INDEX IF NOT EXISTS idx_lexicon_cat ON lexicon(category);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # migração leve: garante colunas novas em bancos antigos
    cols = {r[1] for r in conn.execute("PRAGMA table_info(lexicon)")}
    if "summary" not in cols:
        conn.execute("ALTER TABLE lexicon ADD COLUMN summary TEXT")
    if "loc" not in cols:
        conn.execute("ALTER TABLE lexicon ADD COLUMN loc TEXT")
    conn.commit()
    return conn


def source_exists(conn: sqlite3.Connection, sha256: str) -> bool:
    row = conn.execute("SELECT 1 FROM sources WHERE sha256=?",
                       (sha256,)).fetchone()
    return row is not None


def _upsert_source(conn: sqlite3.Connection, source: Source) -> int:
    conn.execute(
        "INSERT INTO sources(filename,title,sha256,pages) VALUES(?,?,?,?) "
        "ON CONFLICT(filename) DO UPDATE SET "
        "title=excluded.title, sha256=excluded.sha256, pages=excluded.pages, "
        "ingested_at=datetime('now')",
        (source.filename, source.title, source.sha256, source.page_count),
    )
    row = conn.execute("SELECT id FROM sources WHERE filename=?",
                       (source.filename,)).fetchone()
    return row["id"]


def ingest_source(conn: sqlite3.Connection, source: Source,
                  chunks: list[Chunk], lexicon: list[LexEntry],
                  replace: bool = True) -> dict:
    sid = _upsert_source(conn, source)
    if replace:
        conn.execute("DELETE FROM chunks WHERE source_id=?", (sid,))
        conn.execute("DELETE FROM lexicon WHERE source_id=?", (sid,))

    conn.executemany(
        "INSERT INTO chunks(source_id,page,section,kind,content) "
        "VALUES(?,?,?,?,?)",
        [(sid, c.page, c.section, c.kind, c.content) for c in chunks],
    )

    lex_rows = 0
    for e in lexicon:
        try:
            conn.execute(
                "INSERT INTO lexicon(term,norm,category,aliases,meta,summary,loc,source_id,page) "
                "VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(norm,category) DO UPDATE SET "
                "page=CASE WHEN lexicon.page IS NULL THEN excluded.page ELSE lexicon.page END, "
                "loc=CASE WHEN lexicon.page IS NULL THEN excluded.loc ELSE lexicon.loc END, "
                "summary=COALESCE(excluded.summary, lexicon.summary)",
                (e.term, normalize_term(e.term), e.category,
                 json.dumps(e.aliases, ensure_ascii=False),
                 json.dumps(e.meta, ensure_ascii=False),
                 e.summary, e.loc,
                 sid if e.source_filename else None, e.page),
            )
            lex_rows += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return {"source_id": sid, "chunks": len(chunks), "lexicon": lex_rows}


def _run_fts(conn: sqlite3.Connection, match: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT c.content, c.page, c.section, s.title, s.filename, "
        "       bm25(chunks_fts) AS score "
        "FROM chunks_fts "
        "JOIN chunks c ON c.id = chunks_fts.rowid "
        "JOIN sources s ON s.id = c.source_id "
        "WHERE chunks_fts MATCH ? "
        "ORDER BY score LIMIT ?",
        (match, limit * 3),  # pega extra para filtrar índices
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # descarta páginas de índice/sumário (densidade alta de pontos)
        if d["content"].count(".") > len(d["content"]) * 0.15:
            continue
        out.append(d)
    return out[:limit]


def search_fts(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict]:
    """Busca full-text nos chunks. Tenta frase exata; cai para OR se vazio."""
    terms = [t for t in normalize_term(query).split() if len(t) > 1]
    if not terms:
        return []
    # 1) frase exata (melhor precisão)
    if len(terms) > 1:
        phrase = '"' + " ".join(terms) + '"'
        res = _run_fts(conn, phrase, limit)
        if res:
            return res
    # 2) fallback: qualquer termo
    match = " OR ".join(f'"{t}"' for t in terms)
    return _run_fts(conn, match, limit)


def context_for_page(conn: sqlite3.Connection, filename: str,
                     page: int, limit: int = 2) -> list[dict]:
    """Chunks de uma página específica — contexto de uma mecânica detectada."""
    rows = conn.execute(
        "SELECT c.content, c.page, c.section, s.title, s.filename "
        "FROM chunks c JOIN sources s ON s.id=c.source_id "
        "WHERE s.filename=? AND c.page=? "
        "ORDER BY LENGTH(c.content) DESC LIMIT ?",
        (filename, page, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def all_lexicon(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT l.term,l.norm,l.category,l.aliases,l.meta,l.summary,l.loc,l.page,"
        "       s.title,s.filename "
        "FROM lexicon l LEFT JOIN sources s ON s.id=l.source_id"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["aliases"] = json.loads(d["aliases"] or "[]")
        d["meta"] = json.loads(d["meta"] or "{}")
        out.append(d)
    return out


def stats(conn: sqlite3.Connection) -> dict:
    def n(q):
        return conn.execute(q).fetchone()[0]
    by_cat = conn.execute(
        "SELECT category, COUNT(*) c FROM lexicon GROUP BY category ORDER BY c DESC"
    ).fetchall()
    return {
        "sources": n("SELECT COUNT(*) FROM sources"),
        "chunks": n("SELECT COUNT(*) FROM chunks"),
        "lexicon": n("SELECT COUNT(*) FROM lexicon"),
        "por_categoria": {r[0]: r[1] for r in by_cat},
    }
