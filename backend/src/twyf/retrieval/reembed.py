"""Embeds every chunk and note that has no vector for the configured model, in batches. Old vectors are kept."""

import sqlite3
from collections.abc import Callable

from twyf.db.connection import transaction
from twyf.db.repos import embeddings
from twyf.db.repos import notes as notes_repo
from twyf.recording.context import RequestContext
from twyf.retrieval.embedder import Embedder

BATCH = 64


def embed_chunks(
    conn: sqlite3.Connection, embedder: Embedder, rows: list[tuple[int, str, str]], batch: int = BATCH
) -> int:
    """Embeds (chunk id, workspace id, text) rows, one transaction per batch. Returns the vectors written."""
    if embedder.dim == 0 or not rows:
        return 0
    with transaction(conn):
        model = embeddings.model_id(conn, embedder)
    written = 0
    for start in range(0, len(rows), batch):
        part = rows[start : start + batch]
        vectors = embedder.embed([text for _, _, text in part])
        with transaction(conn):
            for workspace_id in dict.fromkeys(ws for _, ws, _ in part):
                embeddings.insert_chunk_vectors(
                    conn, model, workspace_id, [(cid, v) for (cid, ws, _), v in zip(part, vectors, strict=True) if ws == workspace_id]
                )  # fmt: skip
        written += len(part)
    return written


def reembed(
    conn_factory: Callable[[], sqlite3.Connection], ctx: RequestContext, embedder: Embedder, batch: int = BATCH
) -> int:
    if embedder.dim == 0:
        return 0
    conn = conn_factory()
    try:
        with transaction(conn):
            model = embeddings.model_id(conn, embedder)
        missing = embeddings.chunks_without_vectors(conn, model)
        written = embed_chunks(conn, embedder, [(r["id"], r["workspace_id"], r["text"]) for r in missing], batch)
        notes = notes_repo.without_vectors(conn, model)
        for start in range(0, len(notes), batch):
            part = notes[start : start + batch]
            vectors = embedder.embed([r["text"] for r in part])
            with transaction(conn):
                for row, vector in zip(part, vectors, strict=True):
                    notes_repo.set_vector(conn, row["id"], model, row["workspace_id"], vector)
            written += len(part)
        return written
    finally:
        conn.close()
