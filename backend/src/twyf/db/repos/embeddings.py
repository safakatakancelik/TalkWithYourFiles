import builtins
import sqlite3
import struct

from twyf import clock
from twyf.retrieval.embedder import Embedder


def pack(vector: builtins.list[float]) -> bytes:
    """float32 little-endian."""
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes) -> builtins.list[float]:
    return builtins.list(struct.unpack(f"<{len(blob) // 4}f", blob))


def find_model(conn: sqlite3.Connection, embedder: Embedder) -> int | None:
    row = conn.execute(
        "SELECT id FROM embedding_models WHERE name = ? AND version = ?", (embedder.name, embedder.version)
    ).fetchone()
    return row["id"] if row is not None else None


def model_id(conn: sqlite3.Connection, embedder: Embedder) -> int:
    """The embedding_models row of this embedder, inserted when new."""
    found = find_model(conn, embedder)
    if found is not None:
        return found
    cursor = conn.execute(
        "INSERT INTO embedding_models (name, version, dim, created_at) VALUES (?, ?, ?, ?)",
        (embedder.name, embedder.version, embedder.dim, clock.now()),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def insert_chunk_vectors(
    conn: sqlite3.Connection, model: int, workspace_id: str, rows: builtins.list[tuple[int, builtins.list[float]]]
) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO chunk_embeddings (chunk_id, embedding_model_id, workspace_id, vector) VALUES (?, ?, ?, ?)",
        [(chunk_id, model, workspace_id, pack(vector)) for chunk_id, vector in rows],
    )


def chunks_without_vectors(conn: sqlite3.Connection, model: int) -> builtins.list[sqlite3.Row]:
    """Chunks of live files that have no vector for this model."""
    return conn.execute(
        "SELECT c.id, c.workspace_id, c.text FROM chunks c JOIN files f ON f.id = c.file_id AND f.deleted_at IS NULL"
        " WHERE NOT EXISTS (SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.id AND e.embedding_model_id = ?)"
        " ORDER BY c.id",
        (model,),
    ).fetchall()
