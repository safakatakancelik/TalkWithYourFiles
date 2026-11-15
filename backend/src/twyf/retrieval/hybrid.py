"""The only way an agent reaches file content: a fixed number of passages chosen by search."""

import sqlite3
from collections.abc import Callable
from typing import Protocol

from twyf.config import Settings
from twyf.contract.base import Wire
from twyf.db.connection import connect, transaction
from twyf.db.repos import embeddings
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval import keyword
from twyf.retrieval.embedder import Embedder
from twyf.retrieval.vector_index import VectorIndex

CANDIDATES = 20
RRF_K = 60


class Passage(Wire):
    passage_id: str
    chunk_id: int
    file_id: str
    file_name: str
    location: str
    text: str
    score: float


class Retriever(Protocol):
    def search(
        self, ctx: RequestContext, *, workspace_id: str, query: str, file_ids: list[str] | None, k: int
    ) -> list[Passage]: ...


def rrf(lists: list[list[int]]) -> dict[int, float]:
    """Reciprocal rank fusion: score = sum(1 / (60 + rank)) over the lists a chunk appears in. Ranks from 1."""
    scores: dict[int, float] = {}
    for ranked in lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def passages(conn: sqlite3.Connection, scored: list[tuple[int, float]]) -> list[Passage]:
    """Chunks as passages, in the given order. Location is the label of the first block the chunk covers."""
    out: list[Passage] = []
    for chunk_id, score in scored:
        row = conn.execute(
            "SELECT c.id, c.file_id, c.text, c.char_start, c.extraction_id, fv.name FROM chunks c"
            " JOIN extractions x ON x.id = c.extraction_id JOIN file_versions fv ON fv.id = x.file_version_id"
            " WHERE c.id = ?",
            (chunk_id,),
        ).fetchone()
        block = conn.execute(
            "SELECT label FROM blocks WHERE extraction_id = ? AND char_end > ? ORDER BY ordinal LIMIT 1",
            (row["extraction_id"], row["char_start"]),
        ).fetchone()
        out.append(
            Passage(
                passage_id=f"p{chunk_id}", chunk_id=chunk_id, file_id=row["file_id"], file_name=row["name"],
                location=block["label"] if block is not None else "", text=row["text"], score=score,
            )
        )  # fmt: skip
    return out


def first_chunks(conn: sqlite3.Connection, *, workspace_id: str, file_id: str, k: int) -> list[Passage]:
    """The first k chunks of a usable file's current version, in file order. No search."""
    rows = conn.execute(
        "SELECT c.id FROM chunks c JOIN extractions x ON x.id = c.extraction_id"
        " JOIN v_usable_files f ON f.file_version_id = x.file_version_id"
        " WHERE c.workspace_id = ? AND c.file_id = ? AND x.status = 'ok'"
        " ORDER BY CASE x.kind WHEN 'text' THEN 0 WHEN 'ocr' THEN 1 ELSE 2 END, x.created_at, c.ordinal LIMIT ?",
        (workspace_id, file_id, k),
    ).fetchall()
    return passages(conn, [(r[0], 0.0) for r in rows])


def count_chunks(conn: sqlite3.Connection, *, workspace_id: str, file_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM chunks c JOIN extractions x ON x.id = c.extraction_id"
        " JOIN v_usable_files f ON f.file_version_id = x.file_version_id WHERE c.workspace_id = ? AND c.file_id = ?",
        (workspace_id, file_id),
    ).fetchone()[0]


class HybridRetriever:
    def __init__(self, settings: Settings, embedder: Embedder, index: VectorIndex) -> None:
        self.settings = settings
        self.embedder = embedder
        self.index = index

    def _connect(self) -> sqlite3.Connection:
        return connect(self.settings.data_dir / "twyf.db")

    def search(
        self,
        ctx: RequestContext,
        *,
        workspace_id: str,
        query: str,
        file_ids: list[str] | None,
        k: int,
        boost: Callable[[int], float] | None = None,
    ) -> list[Passage]:
        mode = self.settings.retrieval_mode
        conn = self._connect()
        try:
            lists: list[list[int]] = []
            if mode in ("keyword", "hybrid"):
                found = keyword.search(conn, workspace_id=workspace_id, query=query, file_ids=file_ids, k=CANDIDATES)
                lists.append([c for c, _ in found])
            model = embeddings.find_model(conn, self.embedder) if self.embedder.dim else None
            if mode in ("vector", "hybrid") and model is not None:
                [vector] = self.embedder.embed([query])
                found = self.index.search(
                    conn, workspace_id=workspace_id, model_id=model, query=vector, k=CANDIDATES, file_ids=file_ids
                )
                lists.append([c for c, _ in found])
            fused = rrf(lists)
            if boost is not None:
                fused = {c: s * boost(c) for c, s in fused.items()}
            ranked = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:k]
            result = passages(conn, ranked)
            with transaction(conn):
                record(
                    conn, ctx, "retrieval.searched", workspace_id=workspace_id,
                    payload={"query": query, "mode": mode, "file_ids": file_ids, "chunk_ids": [p.chunk_id for p in result]},
                )  # fmt: skip
            return result
        finally:
            conn.close()
