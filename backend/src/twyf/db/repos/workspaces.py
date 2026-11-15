import builtins
import sqlite3

from twyf import clock
from twyf.db.repos import versioned


def insert(conn: sqlite3.Connection, workspace_id: str, user_id: str, name: str) -> None:
    conn.execute(
        "INSERT INTO workspaces (id, user_id, created_at) VALUES (?, ?, ?)", (workspace_id, user_id, clock.now())
    )
    versioned.set_version(conn, "workspace_versions", "workspace_id", workspace_id, {"name": name})


def get(conn: sqlite3.Connection, workspace_id: str) -> sqlite3.Row | None:
    """A live workspace, or None."""
    return conn.execute("SELECT * FROM v_workspaces WHERE id = ?", (workspace_id,)).fetchone()


def list(conn: sqlite3.Connection, user_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT v.* FROM v_workspaces v JOIN workspaces w ON w.id = v.id WHERE v.user_id = ?"
        " ORDER BY v.created_at, w.rowid",
        (user_id,),
    ).fetchall()


def rename(conn: sqlite3.Connection, workspace_id: str, name: str) -> None:
    versioned.set_version(conn, "workspace_versions", "workspace_id", workspace_id, {"name": name})


def soft_delete(conn: sqlite3.Connection, workspace_id: str) -> None:
    conn.execute(
        "UPDATE workspaces SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (clock.now(), workspace_id)
    )
