import sqlite3
import time

from tests.conftest import upload
from twyf import clock
from twyf.contract.models import Workspace
from twyf.contract.operations import CreateWorkspaceInput
from twyf.db.connection import transaction
from twyf.db.repos import notes as repo
from twyf.db.repos import versioned
from twyf.recording.context import RequestContext
from twyf.services import workspaces


def _note(conn: sqlite3.Connection, ws_id: str, file_id: str, note_id: str, text: str = "Note text") -> None:
    fv = conn.execute("SELECT file_version_id FROM v_files WHERE id = ?", (file_id,)).fetchone()[0]
    with transaction(conn):
        repo.insert(
            conn, note_id=note_id, workspace_id=ws_id, file_id=file_id, file_version_id=fv, author_id="u_local",
            kind="interpretation", text=text, citation_ids=[], question_id=None, turn_id=None,
        )  # fmt: skip


def test_create_and_get(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    _note(conn, ws.id, item.id, "n_1", "Read this first")
    row = repo.get(conn, ws.id, "n_1")
    assert row is not None
    assert (row["text"], row["weight"], row["kind"], row["file_version"]) == (
        "Read this first",
        "normal",
        "interpretation",
        1,
    )
    assert conn.execute("SELECT text FROM notes_fts WHERE note_id = 'n_1'").fetchone()[0] == "Read this first"


def test_workspace_isolation(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    _note(conn, ws.id, item.id, "n_1")
    assert repo.get(conn, other.id, "n_1") is None
    assert repo.list(conn, other.id) == []


def test_type2_history(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    _note(conn, ws.id, item.id, "n_1", "One")
    time.sleep(0.002)
    t1 = clock.now()
    for text in ("Two", "Three"):
        time.sleep(0.002)
        with transaction(conn):
            repo.set_text(conn, "n_1", text)
    rows = conn.execute("SELECT * FROM note_versions WHERE note_id = 'n_1' ORDER BY version").fetchall()
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    old = versioned.as_of(conn, "note_versions", "note_id", "n_1", t1)
    assert old is not None and old["text"] == "One"
    assert conn.execute("SELECT text FROM notes_fts WHERE note_id = 'n_1'").fetchall()[0][0] == "Three"


def test_soft_delete_hidden(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Some text here.")
    _note(conn, ws.id, item.id, "n_1")
    with transaction(conn):
        repo.soft_delete(conn, "n_1")
    assert repo.get(conn, ws.id, "n_1") is None and repo.list(conn, ws.id) == []
    assert conn.execute("SELECT deleted_at FROM notes WHERE id = 'n_1'").fetchone()[0] is not None
