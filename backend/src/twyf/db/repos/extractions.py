import builtins
import hashlib
import json
import sqlite3
from dataclasses import dataclass

from twyf import clock
from twyf.files.chunker import ChunkSpan
from twyf.ids import new_id


@dataclass(frozen=True)
class BlockRow:
    ordinal: int
    kind: str
    label: str
    page: int | None
    bbox: tuple[float, float, float, float] | None
    char_start: int
    char_end: int


def find(conn: sqlite3.Connection, file_version_id: str, kind: str, parser: str, parser_version: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM extractions WHERE file_version_id = ? AND kind = ? AND parser = ? AND parser_version = ?",
        (file_version_id, kind, parser, parser_version),
    ).fetchone()
    return row["id"] if row is not None else None


def insert(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    file_version_id: str,
    kind: str,
    parser: str,
    parser_version: str,
    text: str = "",
    blocks: builtins.list[BlockRow] | None = None,
    error: str | None = None,
    turn_id: str | None = None,
) -> str:
    """An extraction and its blocks. An `error` makes it a failed extraction with no text."""
    extraction_id = new_id("x")
    conn.execute(
        "INSERT INTO extractions (id, workspace_id, file_version_id, kind, parser, parser_version, status, error,"
        " text, text_sha256, turn_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            extraction_id, workspace_id, file_version_id, kind, parser, parser_version,
            "failed" if error else "ok", error, text,
            hashlib.sha256(text.encode()).hexdigest() if not error else "", turn_id, clock.now(),
        ),
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO blocks (extraction_id, ordinal, kind, label, page, bbox, char_start, char_end)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (extraction_id, b.ordinal, b.kind, b.label, b.page, json.dumps(b.bbox) if b.bbox else None,
             b.char_start, b.char_end)
            for b in blocks or []
        ],
    )  # fmt: skip
    return extraction_id


def get(conn: sqlite3.Connection, extraction_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM extractions WHERE id = ?", (extraction_id,)).fetchone()


def for_version(conn: sqlite3.Connection, file_version_id: str) -> builtins.list[sqlite3.Row]:
    """Every extraction of a version, oldest first."""
    return conn.execute(
        "SELECT * FROM extractions WHERE file_version_id = ? ORDER BY created_at, rowid", (file_version_id,)
    ).fetchall()


def blocks(conn: sqlite3.Connection, extraction_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute("SELECT * FROM blocks WHERE extraction_id = ? ORDER BY ordinal", (extraction_id,)).fetchall()


def has_chunks(conn: sqlite3.Connection, extraction_id: str) -> bool:
    return conn.execute("SELECT 1 FROM chunks WHERE extraction_id = ? LIMIT 1", (extraction_id,)).fetchone() is not None


def insert_chunks(
    conn: sqlite3.Connection, *, workspace_id: str, extraction_id: str, file_id: str, chunks: builtins.list[ChunkSpan]
) -> builtins.list[int]:
    """Chunks and their rows in chunks_fts. Returns the chunk ids in order."""
    ids: builtins.list[int] = []
    for ordinal, c in enumerate(chunks):
        cursor = conn.execute(
            "INSERT INTO chunks (workspace_id, extraction_id, file_id, ordinal, char_start, char_end, text)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, extraction_id, file_id, ordinal, c.char_start, c.char_end, c.text),
        )
        assert cursor.lastrowid is not None
        ids.append(cursor.lastrowid)
        conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)", (cursor.lastrowid, c.text))
    return ids


def pending_ingestion(conn: sqlite3.Connection) -> builtins.list[str]:
    """Current versions of live files in live workspaces that have no extraction yet."""
    rows = conn.execute(
        "SELECT f.file_version_id FROM v_files f JOIN v_workspaces w ON w.id = f.workspace_id"
        " WHERE NOT EXISTS (SELECT 1 FROM extractions x WHERE x.file_version_id = f.file_version_id)"
        " ORDER BY f.created_at"
    ).fetchall()
    return [r[0] for r in rows]


def textless(conn: sqlite3.Connection) -> builtins.list[tuple[str, str, set[str]]]:
    """Current versions of live files in live workspaces that were parsed but gave no text: each with its file
    type and the parsers already tried."""
    rows = conn.execute(
        "SELECT f.file_version_id, f.file_type, group_concat(x.parser) FROM v_files f"
        " JOIN v_workspaces w ON w.id = f.workspace_id JOIN extractions x ON x.file_version_id = f.file_version_id"
        " WHERE NOT EXISTS (SELECT 1 FROM chunks c JOIN extractions y ON y.id = c.extraction_id"
        "                   WHERE y.file_version_id = f.file_version_id)"
        " GROUP BY f.file_version_id ORDER BY f.created_at"
    ).fetchall()
    return [(r[0], r[1], set(r[2].split(","))) for r in rows]
