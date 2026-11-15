import sqlite3
import time

from twyf import clock
from twyf.db.connection import transaction
from twyf.db.repos import versioned
from twyf.db.repos import workspaces as repo


def _make(conn: sqlite3.Connection, ws_id: str, user: str = "u_local", name: str = "W") -> None:
    with transaction(conn):
        repo.insert(conn, ws_id, user, name)


def test_create_and_get(conn: sqlite3.Connection) -> None:
    _make(conn, "ws_a", name="Alpha")
    row = repo.get(conn, "ws_a")
    assert row is not None and (row["id"], row["name"], row["user_id"]) == ("ws_a", "Alpha", "u_local")


def test_workspace_isolation(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO users VALUES ('u_other', 'Other', '2026-01-01T00:00:00.000Z')")
    _make(conn, "ws_a")
    _make(conn, "ws_b", user="u_other")
    assert [r["id"] for r in repo.list(conn, "u_local")] == ["ws_a"]
    assert [r["id"] for r in repo.list(conn, "u_other")] == ["ws_b"]


def test_type2_history(conn: sqlite3.Connection) -> None:
    _make(conn, "ws_a", name="One")
    time.sleep(0.002)
    t1 = clock.now()
    time.sleep(0.002)
    with transaction(conn):
        repo.rename(conn, "ws_a", "Two")
    time.sleep(0.002)
    t2 = clock.now()
    time.sleep(0.002)
    with transaction(conn):
        repo.rename(conn, "ws_a", "Three")
    rows = conn.execute("SELECT * FROM workspace_versions WHERE workspace_id = 'ws_a' ORDER BY version").fetchall()
    assert [r["version"] for r in rows] == [1, 2, 3]
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    for at, name in ((t1, "One"), (t2, "Two"), (clock.now(), "Three")):
        row = versioned.as_of(conn, "workspace_versions", "workspace_id", "ws_a", at)
        assert row is not None and row["name"] == name


def test_soft_delete_hidden(conn: sqlite3.Connection) -> None:
    _make(conn, "ws_a")
    with transaction(conn):
        repo.soft_delete(conn, "ws_a")
    assert repo.get(conn, "ws_a") is None
    assert repo.list(conn, "u_local") == []
    assert conn.execute("SELECT deleted_at FROM workspaces WHERE id = 'ws_a'").fetchone()[0] is not None
