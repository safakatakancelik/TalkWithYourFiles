import sqlite3

import pytest

from tests.conftest import upload
from twyf.contract.models import Workspace
from twyf.contract.operations import CreateWorkspaceInput
from twyf.db.repos import embeddings
from twyf.recording.context import RequestContext
from twyf.retrieval.embedder import HashEmbedder
from twyf.retrieval.vector_index import NumpyIndex, SqliteVecIndex, get_index
from twyf.services import workspaces

TEXTS = [
    "The lease ends on 30 June 2029.",
    "Rent rises by eight percent each year of the lease.",
    "Bananas and apples are fruit.",
    "The board meets every quarter.",
]


@pytest.fixture
def corpus(ws: Workspace, ctx: RequestContext) -> dict[str, str]:
    ids = {text: upload(ctx, ws.id, f"f{i}.txt", text.encode()).id for i, text in enumerate(TEXTS)}
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    upload(ctx, other.id, "lease.txt", b"The lease ends on 30 June 2029.")
    return ids


def _chunk_file(conn: sqlite3.Connection, chunk_id: int) -> str:
    return conn.execute("SELECT file_id FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


@pytest.mark.parametrize("index", [SqliteVecIndex(), NumpyIndex()], ids=["sqlite-vec", "numpy"])
def test_vector_index_contract(
    index: SqliteVecIndex | NumpyIndex, ws: Workspace, conn: sqlite3.Connection, corpus: dict[str, str]
) -> None:
    embedder = HashEmbedder()
    model = embeddings.model_id(conn, embedder)
    [query] = embedder.embed(["when does the lease end"])
    results = index.search(conn, workspace_id=ws.id, model_id=model, query=query, k=10, file_ids=None)
    assert len(results) == len(TEXTS)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)
    assert _chunk_file(conn, results[0][0]) == corpus[TEXTS[0]]
    assert len(index.search(conn, workspace_id=ws.id, model_id=model, query=query, k=2, file_ids=None)) == 2
    only = [corpus[TEXTS[2]], corpus[TEXTS[3]]]
    limited = index.search(conn, workspace_id=ws.id, model_id=model, query=query, k=10, file_ids=only)
    assert {_chunk_file(conn, c) for c, _ in limited} == set(only)


def test_both_indexes_agree(ws: Workspace, conn: sqlite3.Connection, corpus: dict[str, str]) -> None:
    embedder = HashEmbedder()
    model = embeddings.model_id(conn, embedder)
    for question in ("lease end", "fruit", "board quarter rent"):
        [query] = embedder.embed([question])
        a = SqliteVecIndex().search(conn, workspace_id=ws.id, model_id=model, query=query, k=3, file_ids=None)
        b = NumpyIndex().search(conn, workspace_id=ws.id, model_id=model, query=query, k=3, file_ids=None)
        assert [c for c, _ in a] == [c for c, _ in b]
        assert all(abs(x - y) < 1e-5 for (_, x), (_, y) in zip(a, b, strict=True))


def test_get_index(conn: sqlite3.Connection) -> None:
    assert isinstance(get_index(conn), SqliteVecIndex)
