import sqlite3

from tests.conftest import EventsHelper, add_version, upload
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.recording.context import RequestContext
from twyf.retrieval import keyword
from twyf.retrieval.fusion import rrf
from twyf.retrieval.hybrid import HybridRetriever, first_chunks


def _file_of(conn: sqlite3.Connection, chunk_id: int) -> str:
    return conn.execute("SELECT file_id FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]


def test_fts_query() -> None:
    assert keyword.fts_query("What is the lease's end-date? (2029)") == '"lease" OR "end" OR "date" OR "2029"'
    assert keyword.fts_query("a ? !") == ""


def test_keyword_search(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    lease = upload(ctx, ws.id, "lease.txt", b"The tenancy ends in June.\n\nNothing else here.")
    upload(ctx, ws.id, "fruit.txt", b"Bananas are yellow.")
    results = keyword.search(conn, workspace_id=ws.id, query="tenancy", file_ids=None, k=5)
    assert results and _file_of(conn, results[0][0]) == lease.id
    for query in ('"unbalanced', "AND OR NOT", "x*y:z(", "NEAR(a b)", "'; DROP TABLE chunks; --"):
        keyword.search(conn, workspace_id=ws.id, query=query, file_ids=None, k=5)
    assert keyword.search(conn, workspace_id=ws.id, query="tenancy", file_ids=["f_other"], k=5) == []


def test_hybrid_fusion() -> None:
    both = rrf([[1, 2, 3], [4, 2, 5]])
    assert both[2] > both[1] and both[2] > both[4]
    assert both[1] == 1 / 61


def test_hybrid_search_returns_passages(
    ws: Workspace, ctx: RequestContext, retriever: HybridRetriever, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "lease.md", b"# Term\n\nThe lease ends on 30 June 2029.\n\n# Rent\n\nRent rises by 8%.")
    [first, *_] = retriever.search(ctx, workspace_id=ws.id, query="when does the lease end", file_ids=None, k=2)
    assert (first.file_id, first.file_name, first.passage_id) == (item.id, "lease.md", f"p{first.chunk_id}")
    assert "30 June 2029" in first.text
    assert first.location == "Term"
    [searched] = events("retrieval.searched")
    assert searched.payload["mode"] == "hybrid" and searched.payload["chunk_ids"][0] == first.chunk_id


def test_boost_reorders(ws: Workspace, ctx: RequestContext, retriever: HybridRetriever) -> None:
    upload(ctx, ws.id, "a.txt", b"Payment terms are thirty days.")
    upload(ctx, ws.id, "b.txt", b"Payment terms are thirty days!")
    plain = retriever.search(ctx, workspace_id=ws.id, query="payment terms", file_ids=None, k=2)
    loser = plain[1].chunk_id
    boosted = retriever.search(
        ctx, workspace_id=ws.id, query="payment terms", file_ids=None, k=2, boost=lambda c: 2.0 if c == loser else 1.0
    )
    assert boosted[0].chunk_id == loser


def test_only_current_versions_searched(ws: Workspace, ctx: RequestContext, retriever: HybridRetriever) -> None:
    item = upload(ctx, ws.id, "plan.txt", b"The budget is forty thousand.")
    add_version(ctx, ws.id, item.id, "plan.txt", b"The budget is fifty thousand.")
    found = retriever.search(ctx, workspace_id=ws.id, query="budget forty fifty thousand", file_ids=None, k=10)
    assert [p.text for p in found] == ["The budget is fifty thousand."]


def test_unusable_files_not_searched(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, retriever: HybridRetriever
) -> None:
    from twyf.files.integrity import verify_workspace

    gone = upload(ctx, ws.id, "gone.txt", b"Shared word alpha.")
    damaged = upload(ctx, ws.id, "damaged.txt", b"Shared word alpha too.")
    fine = upload(ctx, ws.id, "fine.txt", b"Shared word alpha here.")
    for item, change in ((gone, None), (damaged, b"changed")):
        location = conn.execute("SELECT location FROM v_files WHERE id = ?", (item.id,)).fetchone()[0]
        path = settings.data_dir / location
        if change is None:
            path.unlink()
        else:
            path.write_bytes(change)
    verify_workspace(conn, ctx, ws.id)
    found = retriever.search(ctx, workspace_id=ws.id, query="shared word alpha", file_ids=None, k=10)
    assert {p.file_id for p in found} == {fine.id}
    assert [p.file_id for p in first_chunks(conn, workspace_id=ws.id, file_id=gone.id, k=5)] == []


def test_keyword_mode_and_first_chunks(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    from twyf.retrieval.embedder import NullEmbedder
    from twyf.retrieval.vector_index import NumpyIndex

    text = "\n\n".join(f"Section {i}: " + "filler " * 190 for i in range(5))
    item = upload(ctx, ws.id, "long.txt", text.encode())
    opening = first_chunks(conn, workspace_id=ws.id, file_id=item.id, k=2)
    assert [p.text.split(":")[0] for p in opening] == ["Section 0", "Section 1"]
    keyword_only = HybridRetriever(
        settings.model_copy(update={"retrieval_mode": "keyword"}), NullEmbedder(), NumpyIndex()
    )
    assert keyword_only.search(ctx, workspace_id=ws.id, query="Section filler", file_ids=[item.id], k=3)
