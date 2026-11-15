import sqlite3

import pytest

from tests.conftest import EventsHelper, upload
from twyf.contract.models import Workspace
from twyf.db.repos import embeddings
from twyf.recording.context import RequestContext
from twyf.retrieval import reembed as reembed_module
from twyf.retrieval.embedder import HashEmbedder
from twyf.retrieval.reembed import reembed
from twyf.retrieval.vector_index import get_index
from twyf.services import state


def test_ingest_batches(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper, monkeypatch: pytest.MonkeyPatch
) -> None:
    batches: list[tuple[int, bool]] = []
    original = embeddings.insert_chunk_vectors

    def spy(c: sqlite3.Connection, model: int, workspace_id: str, rows: list[tuple[int, list[float]]]) -> None:
        batches.append((len(rows), c.in_transaction))
        original(c, model, workspace_id, rows)

    monkeypatch.setattr(reembed_module.embeddings, "insert_chunk_vectors", spy)
    text = "\n\n".join(f"Paragraph {i} " + "word " * 198 for i in range(200))
    upload(ctx, ws.id, "long.txt", text.encode())
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 200
    assert batches == [(64, True), (64, True), (64, True), (8, True)]
    assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 200
    assert len(events("file.indexed")) == 1


class RenamedHash(HashEmbedder):
    name = "hash-v2"


def test_reembed_for_new_model(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    upload(ctx, ws.id, "a.txt", b"The lease ends on 30 June 2029.\n\nRent rises by eight percent.")
    upload(ctx, ws.id, "b.txt", b"Bananas are yellow.")
    old_model = embeddings.model_id(conn, HashEmbedder())
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    new = RenamedHash()
    assert reembed(state.connect, ctx.as_actor("system"), new, batch=1) == chunk_count
    new_model = embeddings.find_model(conn, new)
    assert new_model is not None and new_model != old_model
    counts = dict(
        conn.execute("SELECT embedding_model_id, COUNT(*) FROM chunk_embeddings GROUP BY embedding_model_id").fetchall()
    )
    assert counts == {old_model: chunk_count, new_model: chunk_count}
    [query] = new.embed(["lease"])
    results = get_index(conn).search(conn, workspace_id=ws.id, model_id=new_model, query=query, k=5, file_ids=None)
    assert len(results) == chunk_count
    assert reembed(state.connect, ctx.as_actor("system"), new) == 0
