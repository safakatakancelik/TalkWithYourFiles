import sqlite3
import time

from twyf import clock
from twyf.db.connection import transaction
from twyf.db.repos import files as repo
from twyf.db.repos import versioned
from twyf.db.repos import workspaces as ws_repo


def _setup(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        ws_repo.insert(conn, "ws_a", "u_local", "A")
        ws_repo.insert(conn, "ws_b", "u_local", "B")


def _add(conn: sqlite3.Connection, ws: str, file_id: str, fv: str, name: str = "a.txt", sha: str = "1" * 64) -> None:
    with transaction(conn):
        if repo.get(conn, ws, file_id) is None:
            repo.insert_file(conn, ws, file_id)
        repo.add_version(
            conn, workspace_id=ws, file_id=file_id, file_version_id=fv, sha256=sha, name=name, file_type="txt",
            size_bytes=3, location=f"files/{sha[:2]}/{sha}", mtime_ns=1,
        )  # fmt: skip


def test_create_and_get(conn: sqlite3.Connection) -> None:
    _setup(conn)
    _add(conn, "ws_a", "f_1", "fv_1")
    row = repo.get(conn, "ws_a", "f_1")
    assert row is not None
    assert (row["file_version_id"], row["version"], row["name"], row["availability"]) == ("fv_1", 1, "a.txt", "ok")


def test_workspace_isolation(conn: sqlite3.Connection) -> None:
    _setup(conn)
    _add(conn, "ws_a", "f_1", "fv_1")
    assert repo.get(conn, "ws_b", "f_1") is None
    assert repo.list(conn, "ws_b") == []
    assert repo.find_duplicate(conn, "ws_b", "a.txt", "1" * 64) is None
    assert repo.find_duplicate(conn, "ws_a", "a.txt", "1" * 64) is not None


def test_type2_history(conn: sqlite3.Connection) -> None:
    _setup(conn)
    _add(conn, "ws_a", "f_1", "fv_1", name="one.txt", sha="1" * 64)
    time.sleep(0.002)
    t1 = clock.now()
    time.sleep(0.002)
    _add(conn, "ws_a", "f_1", "fv_2", name="two.txt", sha="2" * 64)
    _add(conn, "ws_a", "f_1", "fv_3", name="three.txt", sha="3" * 64)
    rows = conn.execute("SELECT * FROM file_versions WHERE file_id = 'f_1' ORDER BY version").fetchall()
    assert [r["version"] for r in rows] == [1, 2, 3]
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    old = versioned.as_of(conn, "file_versions", "file_id", "f_1", t1)
    assert old is not None and old["name"] == "one.txt"
    current = repo.get(conn, "ws_a", "f_1")
    assert current is not None and current["name"] == "three.txt"


def test_soft_delete_hidden(conn: sqlite3.Connection) -> None:
    _setup(conn)
    _add(conn, "ws_a", "f_1", "fv_1")
    with transaction(conn):
        repo.soft_delete(conn, "f_1")
    assert repo.get(conn, "ws_a", "f_1") is None
    assert repo.list(conn, "ws_a") == []
    assert conn.execute("SELECT COUNT(*) FROM files WHERE id = 'f_1'").fetchone()[0] == 1
    version = repo.version(conn, "fv_1")
    assert version is not None and version["availability"] == "ok"
