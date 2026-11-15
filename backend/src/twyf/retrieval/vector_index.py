"""Exact vector search over chunk_embeddings, by sqlite-vec or by numpy. Only chunks of usable current versions."""

import sqlite3
from typing import Protocol

import numpy as np

from twyf.db.connection import vec_loaded
from twyf.db.repos.embeddings import pack

_FROM = (
    " FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id"
    " JOIN extractions x ON x.id = c.extraction_id"
    " JOIN v_usable_files f ON f.file_version_id = x.file_version_id"
    " WHERE e.workspace_id = ? AND e.embedding_model_id = ?"
)


def _filter(workspace_id: str, model_id: int, file_ids: list[str] | None) -> tuple[str, list[object]]:
    sql = _FROM
    args: list[object] = [workspace_id, model_id]
    if file_ids is not None:
        sql += f" AND c.file_id IN ({', '.join('?' for _ in file_ids)})"
        args += file_ids
    return sql, args


class VectorIndex(Protocol):
    def search(
        self, conn: sqlite3.Connection, *, workspace_id: str, model_id: int, query: list[float], k: int,
        file_ids: list[str] | None,
    ) -> list[tuple[int, float]]: ...  # (chunk_id, similarity), best first  # fmt: skip


class SqliteVecIndex:
    def search(
        self, conn: sqlite3.Connection, *, workspace_id: str, model_id: int, query: list[float], k: int,
        file_ids: list[str] | None,
    ) -> list[tuple[int, float]]:  # fmt: skip
        where, args = _filter(workspace_id, model_id, file_ids)
        rows = conn.execute(
            "SELECT c.id, 1 - vec_distance_cosine(e.vector, ?) AS similarity" + where
            + " ORDER BY similarity DESC, c.id LIMIT ?",
            [pack(query), *args, k],
        ).fetchall()  # fmt: skip
        return [(r[0], float(r[1])) for r in rows]


class NumpyIndex:
    def search(
        self, conn: sqlite3.Connection, *, workspace_id: str, model_id: int, query: list[float], k: int,
        file_ids: list[str] | None,
    ) -> list[tuple[int, float]]:  # fmt: skip
        where, args = _filter(workspace_id, model_id, file_ids)
        rows = conn.execute("SELECT c.id, e.vector" + where + " ORDER BY c.id", args).fetchall()
        if not rows:
            return []
        matrix = np.stack([np.frombuffer(r[1], dtype="<f4") for r in rows])
        scores = matrix @ np.asarray(query, dtype="<f4")
        order = sorted(range(len(rows)), key=lambda i: (-float(scores[i]), rows[i][0]))[:k]
        return [(rows[i][0], float(scores[i])) for i in order]


def get_index(conn: sqlite3.Connection) -> VectorIndex:
    return SqliteVecIndex() if vec_loaded(conn) else NumpyIndex()
