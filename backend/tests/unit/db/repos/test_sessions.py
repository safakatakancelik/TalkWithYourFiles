import sqlite3
import time

from twyf import clock
from twyf.contract.models import Workspace
from twyf.contract.operations import CreateWorkspaceInput
from twyf.db.connection import transaction
from twyf.db.repos import sessions as repo
from twyf.db.repos import versioned
from twyf.recording.context import RequestContext
from twyf.services import workspaces


def test_create_and_get(ws: Workspace, conn: sqlite3.Connection) -> None:
    with transaction(conn):
        repo.insert(conn, ws.id, "s_1", "Lease")
    row = repo.get(conn, ws.id, "s_1")
    assert row is not None and (row["title"], row["message_count"]) == ("Lease", 0)


def test_workspace_isolation(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    with transaction(conn):
        repo.insert(conn, ws.id, "s_1", "Lease")
    assert repo.get(conn, other.id, "s_1") is None and repo.list(conn, other.id) == []
    assert repo.messages(conn, other.id, "s_1") == []


def test_type2_history(ws: Workspace, conn: sqlite3.Connection) -> None:
    with transaction(conn):
        repo.insert(conn, ws.id, "s_1", "One")
    time.sleep(0.002)
    t1 = clock.now()
    for title in ("Two", "Three"):
        time.sleep(0.002)
        with transaction(conn):
            repo.rename(conn, "s_1", title)
    rows = conn.execute("SELECT * FROM session_versions WHERE session_id = 's_1' ORDER BY version").fetchall()
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    old = versioned.as_of(conn, "session_versions", "session_id", "s_1", t1)
    assert old is not None and old["title"] == "One"


def test_soft_delete_hidden(ws: Workspace, conn: sqlite3.Connection) -> None:
    with transaction(conn):
        repo.insert(conn, ws.id, "s_1", "Lease")
        repo.soft_delete(conn, "s_1")
    assert repo.get(conn, ws.id, "s_1") is None and repo.list(conn, ws.id) == []
    assert conn.execute("SELECT deleted_at FROM sessions WHERE id = 's_1'").fetchone()[0] is not None
