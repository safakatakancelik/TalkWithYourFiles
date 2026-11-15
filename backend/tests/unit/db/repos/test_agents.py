import sqlite3
import time

from twyf import clock
from twyf.db.connection import transaction
from twyf.db.repos import agents as repo
from twyf.db.repos import versioned
from twyf.db.repos import workspaces as ws_repo


def _setup(conn: sqlite3.Connection) -> int:
    with transaction(conn):
        ws_repo.insert(conn, "ws_a", "u_local", "A")
        ws_repo.insert(conn, "ws_b", "u_local", "B")
        conn.execute("INSERT INTO agent_definitions (slug, agent_kind) VALUES ('translator', 'translator')")
    return conn.execute("SELECT id FROM agent_definitions").fetchone()[0]


def test_create_and_get(conn: sqlite3.Connection) -> None:
    did = _setup(conn)
    with transaction(conn):
        repo.insert(conn, "ws_a", "a_1", "translator", "T1", "generic", did)
    agent = repo.get(conn, "ws_a", "a_1")
    assert agent is not None
    assert (agent.name, agent.specialty, agent.agent_kind, agent.definition_id) == ("T1", "generic", "translator", did)
    assert conn.execute("SELECT actor_kind, workspace_id FROM actors WHERE id = 'a_1'").fetchone()[:] == (
        "agent",
        "ws_a",
    )


def test_workspace_isolation(conn: sqlite3.Connection) -> None:
    did = _setup(conn)
    with transaction(conn):
        repo.insert(conn, "ws_a", "a_1", "translator", "T1", "generic", did)
    assert repo.get(conn, "ws_b", "a_1") is None
    assert repo.list(conn, "ws_b") == []
    assert [a.id for a in repo.list(conn, "ws_a")] == ["a_1"]


def test_type2_history(conn: sqlite3.Connection) -> None:
    did = _setup(conn)
    with transaction(conn):
        repo.insert(conn, "ws_a", "a_1", "translator", "One", "generic", did)
    time.sleep(0.002)
    t1 = clock.now()
    for name in ("Two", "Three"):
        time.sleep(0.002)
        agent = repo.get(conn, "ws_a", "a_1")
        assert agent is not None
        with transaction(conn):
            repo.set_version(conn, agent, name=name)
    rows = conn.execute("SELECT * FROM agent_versions WHERE agent_id = 'a_1' ORDER BY version").fetchall()
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    row = versioned.as_of(conn, "agent_versions", "agent_id", "a_1", t1)
    assert row is not None and row["name"] == "One"


def test_soft_delete_hidden(conn: sqlite3.Connection) -> None:
    did = _setup(conn)
    with transaction(conn):
        repo.insert(conn, "ws_a", "a_1", "translator", "T1", "generic", did)
        repo.soft_delete(conn, "a_1")
    assert repo.get(conn, "ws_a", "a_1") is None
    assert repo.list(conn, "ws_a") == []
    assert conn.execute("SELECT deleted_at FROM agents WHERE id = 'a_1'").fetchone()[0] is not None
    assert repo.last_name(conn, "a_1") == "T1"
