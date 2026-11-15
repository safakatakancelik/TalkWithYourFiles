import sqlite3

from tests.conftest import add_version, agent_note, cite, upload
from twyf.config import Settings
from twyf.contract.models import Weight, Workspace
from twyf.contract.operations import AddNoteInput, SetNoteWeightInput
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import embeddings
from twyf.files.integrity import verify_workspace
from twyf.recording.context import RequestContext
from twyf.retrieval.embedder import HashEmbedder
from twyf.retrieval.hybrid import HybridRetriever
from twyf.retrieval.reembed import reembed
from twyf.retrieval.weights import MAX_NOTES, notes_for_turn, passage_boost
from twyf.services import notes, state


def _note(ctx: RequestContext, ws: Workspace, file_id: str, text: str, weight: Weight = "normal") -> str:
    note = notes.add(ctx, AddNoteInput(ws=ws.id, file_id=file_id, text=text))
    if weight != "normal":
        notes.set_weight(ctx, SetNoteWeightInput(ws=ws.id, note_ids=[note.id], weight=weight))
    return note.id


def test_weight_off_excluded(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Alpha text.")
    b = upload(ctx, ws.id, "b.txt", b"Beta text.")
    off = _note(ctx, ws, a.id, "Quarterly revenue guidance", "off")
    on = _note(ctx, ws, a.id, "Quarterly revenue other", "normal")
    off_other = _note(ctx, ws, b.id, "Quarterly revenue elsewhere", "off")
    got = [n.note_id for n in notes_for_turn(conn, workspace_id=ws.id, file_ids=[a.id], query="quarterly revenue")]
    assert on in got and off not in got and off_other not in got


def test_note_order_and_budget(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Alpha text.")
    low = _note(ctx, ws, a.id, "low one", "low")
    normal_old = _note(ctx, ws, a.id, "normal old")
    high = _note(ctx, ws, a.id, "high one", "high")
    normal_new = _note(ctx, ws, a.id, "normal new")
    got = [n.note_id for n in notes_for_turn(conn, workspace_id=ws.id, file_ids=[a.id], query="zzz")]
    assert got == [high, normal_new, normal_old, low]
    for i in range(MAX_NOTES):
        _note(ctx, ws, a.id, f"filler {i}")
    got = [n.note_id for n in notes_for_turn(conn, workspace_id=ws.id, file_ids=[a.id], query="zzz")]
    assert len(got) == MAX_NOTES and got[0] == high and low not in got
    b = upload(ctx, ws.id, "b.txt", b"Beta text.")
    big_low = _note(ctx, ws, b.id, "x" * 3000, "low")
    big = [_note(ctx, ws, b.id, "y" * 2500) for _ in range(2)]
    got = [n.note_id for n in notes_for_turn(conn, workspace_id=ws.id, file_ids=[b.id], query="zzz")]
    assert got[:2] == list(reversed(big)) and big_low not in got


def test_notes_from_other_files_and_earlier_versions(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection
) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Alpha text.")
    b = upload(ctx, ws.id, "b.txt", b"Beta text.")
    on_a = _note(ctx, ws, a.id, "General remark")
    elsewhere = _note(ctx, ws, b.id, "The supplier contract renews yearly")
    add_version(ctx, ws.id, a.id, "a.txt", b"Alpha text, second version.")
    got = notes_for_turn(conn, workspace_id=ws.id, file_ids=[a.id], query="supplier contract")
    by_id = {n.note_id: n for n in got}
    assert by_id[on_a].earlier_version is True and by_id[on_a].file_version == 1
    assert elsewhere in by_id and by_id[elsewhere].file_name == "b.txt"


def test_high_note_boosts_passage(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, retriever: HybridRetriever
) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Payment terms are thirty days net.")
    b = upload(ctx, ws.id, "b.txt", b"Payment terms are thirty days net!")
    plain = retriever.search(ctx, workspace_id=ws.id, query="payment terms", file_ids=None, k=2)
    loser = plain[1]
    agent = agents_repo.list(conn, ws.id, "translator")[0].id
    cid = cite(conn, ctx, ws.id, loser.file_id, "Payment terms are thirty days", agent)
    note = agent_note(conn, ctx, ws.id, loser.file_id, "Terms are thirty days", [cid], agent)
    notes.set_weight(ctx, SetNoteWeightInput(ws=ws.id, note_ids=[note], weight="high"))
    assert passage_boost(conn, ws.id)(loser.chunk_id) == 1.25
    assert passage_boost(conn, ws.id)(plain[0].chunk_id) == 1.0
    boosted = retriever.search(ctx, workspace_id=ws.id, query="payment terms", file_ids=None, k=2)
    assert boosted[0].chunk_id == loser.chunk_id
    assert {a.id, b.id} == {p.file_id for p in boosted}


def test_unusable_file_notes_hidden(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    gone = upload(ctx, ws.id, "gone.txt", b"Gone text.")
    fine = upload(ctx, ws.id, "fine.txt", b"Fine text.")
    hidden = _note(ctx, ws, gone.id, "Shared remark about rent")
    shown = _note(ctx, ws, fine.id, "Shared remark about rent too")
    location = conn.execute("SELECT location FROM v_files WHERE id = ?", (gone.id,)).fetchone()[0]
    (settings.data_dir / location).unlink()
    verify_workspace(conn, ctx, ws.id)
    got = [
        n.note_id for n in notes_for_turn(conn, workspace_id=ws.id, file_ids=[gone.id, fine.id], query="rent remark")
    ]
    assert got == [shown] and hidden not in got


class RenamedHash(HashEmbedder):
    name = "hash-v2"


def test_reembed_covers_notes(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Alpha text.")
    _note(ctx, ws, a.id, "A note to embed")
    old = embeddings.model_id(conn, HashEmbedder())
    assert conn.execute("SELECT COUNT(*) FROM note_embeddings WHERE embedding_model_id = ?", (old,)).fetchone()[0] == 1
    reembed(state.connect, ctx.as_actor("system"), RenamedHash())
    with transaction(conn):
        new = embeddings.model_id(conn, RenamedHash())
    assert conn.execute("SELECT COUNT(*) FROM note_embeddings WHERE embedding_model_id = ?", (new,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM note_embeddings").fetchone()[0] == 2
