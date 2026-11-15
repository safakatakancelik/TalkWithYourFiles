import builtins
import json
import sqlite3

from twyf import clock
from twyf.db.repos import versioned


def insert(conn: sqlite3.Connection, workspace_id: str, session_id: str, title: str) -> None:
    now = clock.now()
    conn.execute(
        "INSERT INTO sessions (id, workspace_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, workspace_id, now, now),
    )
    versioned.set_version(conn, "session_versions", "session_id", session_id, {"title": title})


def get(conn: sqlite3.Connection, workspace_id: str, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM v_sessions WHERE workspace_id = ? AND id = ?", (workspace_id, session_id)
    ).fetchone()


def list(conn: sqlite3.Connection, workspace_id: str) -> builtins.list[sqlite3.Row]:
    """Latest first."""
    return conn.execute(
        "SELECT v.* FROM v_sessions v JOIN sessions s ON s.id = v.id WHERE v.workspace_id = ?"
        " ORDER BY v.updated_at DESC, s.rowid DESC",
        (workspace_id,),
    ).fetchall()


def rename(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    versioned.set_version(conn, "session_versions", "session_id", session_id, {"title": title})


def soft_delete(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("UPDATE sessions SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (clock.now(), session_id))


def insert_message(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    workspace_id: str,
    session_id: str,
    role: str,
    text: str,
    question_id: str | None,
    citation_ids: builtins.list[str],
    unverified: builtins.list[dict[str, str]] | None,
) -> str:
    now = clock.now()
    conn.execute(
        "INSERT INTO messages (id, workspace_id, session_id, question_id, role, text, unverified, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (message_id, workspace_id, session_id, question_id, role, text,
         json.dumps(unverified) if unverified is not None else None, now),
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO message_citations (message_id, citation_id, n) VALUES (?, ?, ?)",
        [(message_id, cid, n) for n, cid in enumerate(citation_ids, start=1)],
    )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    return message_id


def messages(conn: sqlite3.Connection, workspace_id: str, session_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM messages WHERE workspace_id = ? AND session_id = ? ORDER BY created_at, rowid",
        (workspace_id, session_id),
    ).fetchall()


def message_citations(conn: sqlite3.Connection, message_id: str) -> builtins.list[tuple[str, int]]:
    rows = conn.execute("SELECT citation_id, n FROM message_citations WHERE message_id = ? ORDER BY n", (message_id,))
    return [(r[0], r[1]) for r in rows]
