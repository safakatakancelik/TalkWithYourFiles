import sqlite3

import pytest

from tests.conftest import EventsHelper, add_version, agent_note, cite, upload
from twyf.citations.check import check
from twyf.contract.models import Workspace
from twyf.contract.operations import (
    AddNoteInput,
    DeleteFileInput,
    DeleteNoteInput,
    EditNoteInput,
    ListNotesInput,
    SetNoteWeightInput,
)
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.recording.context import RequestContext
from twyf.services import files, notes
from twyf.services.errors import ServiceError
from twyf.services.notes import create_agent_note


def _translator(conn: sqlite3.Connection, ws: Workspace) -> str:
    return agents_repo.list(conn, ws.id, "translator")[0].id


def test_add_and_list(ws: Workspace, ctx: RequestContext, events: EventsHelper) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    note = notes.add(ctx, AddNoteInput(ws=ws.id, file_id=item.id, text="Check page two"))
    assert (note.kind, note.author_id, note.citations, note.weight) == ("interpretation", "user", [], "normal")
    assert (note.author_name, note.file_version) == ("Local user", 1)
    assert notes.list(ctx, ListNotesInput(ws=ws.id)) == [note]
    assert events("note.created")[0].entity_id == note.id
    with pytest.raises(ServiceError) as raised:
        notes.add(ctx, AddNoteInput(ws=ws.id, file_id="f_nope", text="x"))
    assert raised.value.code == "not_found"


def test_agent_note_rules(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"The lease ends on 30 June 2029.")
    b = upload(ctx, ws.id, "b.txt", b"Rent rises by eight percent.")
    agent = _translator(conn, ws)
    in_a = cite(conn, ctx, ws.id, a.id, "ends on 30 June 2029", agent)
    in_b = cite(conn, ctx, ws.id, b.id, "rises by eight percent", agent)
    for kind, ids in (("summary", []), ("finding", []), ("finding", [in_b])):
        with pytest.raises(ServiceError) as raised:
            agent_note(conn, ctx, ws.id, a.id, "Text", ids, agent, kind=kind)
        assert raised.value.code == "validation"
    agent_note(conn, ctx, ws.id, a.id, "Guidance only", [], agent, kind="interpretation")
    note_id = agent_note(conn, ctx, ws.id, a.id, "It ends in 2029 [1].", [in_a], agent)
    [listed] = [n for n in notes.list(ctx, ListNotesInput(ws=ws.id)) if n.id == note_id]
    assert listed.author_id == agent and listed.author_name == "Translator"
    assert [(c.n, c.id) for c in listed.citations] == [(1, in_a)]


def test_agent_note_in_a_question_carries_its_numbers(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper
) -> None:
    a = upload(ctx, ws.id, "a.txt", b"The lease ends on 30 June 2029.")
    agent = _translator(conn, ws)
    cid = cite(conn, ctx, ws.id, a.id, "ends on 30 June 2029", agent)
    with transaction(conn):
        conn.execute(
            "INSERT INTO sessions VALUES ('s_1', ?, '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z', NULL)",
            (ws.id,),
        )
        conn.execute("INSERT INTO questions (id, workspace_id, session_id, state, max_rounds, config_version_id, runtime, started_at)"
                     " VALUES ('q_1', ?, 's_1', 'working', 3, 1, 'fake', '2026-01-01T00:00:00.000Z')", (ws.id,))  # fmt: skip
        create_agent_note(
            conn, ctx.as_actor(agent), workspace_id=ws.id, file_id=a.id, author_id=agent, kind="finding",
            text="Ends 2029 [4].", citation_ids=[cid], numbers=[4], question_id="q_1", turn_id=None,
        )  # fmt: skip
    from twyf.db.repos.events import wire_events

    [(_, event)] = wire_events(conn, "q_1")
    assert event.type == "note" and [c.n for c in event.note.citations] == [4]


def test_edit_and_delete(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    item = upload(ctx, ws.id, "a.txt", b"The lease ends on 30 June 2029.")
    mine = notes.add(ctx, AddNoteInput(ws=ws.id, file_id=item.id, text="First"))
    edited = notes.edit(ctx, EditNoteInput(ws=ws.id, note_id=mine.id, text="Second"))
    assert edited.text == "Second"
    assert events("note.edited")[0].payload == {"old": "First", "new": "Second"}
    assert conn.execute("SELECT COUNT(*) FROM note_versions WHERE note_id = ?", (mine.id,)).fetchone()[0] == 2
    agent = _translator(conn, ws)
    theirs = agent_note(
        conn, ctx, ws.id, item.id, "Ends 2029", [cite(conn, ctx, ws.id, item.id, "30 June 2029", agent)], agent
    )
    with pytest.raises(ServiceError) as raised:
        notes.edit(ctx, EditNoteInput(ws=ws.id, note_id=theirs, text="Changed"))
    assert raised.value.code == "validation"
    notes.delete(ctx, DeleteNoteInput(ws=ws.id, note_id=theirs))
    assert [n.id for n in notes.list(ctx, ListNotesInput(ws=ws.id))] == [mine.id]
    with pytest.raises(ServiceError) as raised:
        notes.delete(ctx, DeleteNoteInput(ws=ws.id, note_id=theirs))
    assert raised.value.code == "not_found"


def test_set_weight(ws: Workspace, ctx: RequestContext, events: EventsHelper) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    ids = [notes.add(ctx, AddNoteInput(ws=ws.id, file_id=item.id, text=f"Note {i}")).id for i in range(3)]
    notes.set_weight(ctx, SetNoteWeightInput(ws=ws.id, note_ids=ids, weight="high"))
    notes.set_weight(ctx, SetNoteWeightInput(ws=ws.id, note_ids=ids[:1], weight="high"))
    set_events = events("note.weight_set")
    assert len(set_events) == 3 and all(e.payload == {"old": "normal", "new": "high"} for e in set_events)
    assert {n.weight for n in notes.list(ctx, ListNotesInput(ws=ws.id))} == {"high"}
    with pytest.raises(ServiceError):
        notes.set_weight(ctx, SetNoteWeightInput(ws=ws.id, note_ids=["n_nope"], weight="low"))


def test_deleted_file_hides_notes(ws: Workspace, ctx: RequestContext) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    notes.add(ctx, AddNoteInput(ws=ws.id, file_id=item.id, text="Note"))
    files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=item.id))
    assert notes.list(ctx, ListNotesInput(ws=ws.id)) == []


def test_everything_points_at_its_version(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "plan.txt", b"The budget is forty thousand pounds.")
    v1 = conn.execute("SELECT file_version_id FROM v_files WHERE id = ?", (item.id,)).fetchone()[0]
    agent = _translator(conn, ws)
    old_citation = cite(conn, ctx, ws.id, item.id, "forty thousand pounds", agent)
    old_note = agent_note(conn, ctx, ws.id, item.id, "Budget is forty thousand", [old_citation], agent)
    add_version(ctx, ws.id, item.id, "plan.txt", b"The budget is fifty thousand pounds.")
    v2 = conn.execute("SELECT file_version_id FROM v_files WHERE id = ?", (item.id,)).fetchone()[0]
    assert conn.execute("SELECT file_version_id FROM notes WHERE id = ?", (old_note,)).fetchone()[0] == v1
    assert conn.execute("SELECT file_version_id FROM citations WHERE id = ?", (old_citation,)).fetchone()[0] == v1
    assert check(conn, old_citation).ok
    new_citation = cite(conn, ctx, ws.id, item.id, "fifty thousand pounds", agent)
    new_note = agent_note(conn, ctx, ws.id, item.id, "Budget is fifty thousand", [new_citation], agent)
    assert conn.execute("SELECT file_version_id FROM citations WHERE id = ?", (new_citation,)).fetchone()[0] == v2
    assert conn.execute("SELECT file_version_id FROM notes WHERE id = ?", (new_note,)).fetchone()[0] == v2
    listed = {n.id: n.file_version for n in notes.list(ctx, ListNotesInput(ws=ws.id))}
    assert listed == {old_note: 1, new_note: 2}
