import builtins
import sqlite3
from dataclasses import dataclass

from twyf import clock
from twyf.db.repos import versioned


@dataclass(frozen=True)
class AgentRow:
    id: str
    workspace_id: str
    agent_kind: str
    agent_version_id: int
    name: str
    specialty: str
    definition_id: int
    created_at: str


def _row(row: sqlite3.Row) -> AgentRow:
    return AgentRow(
        id=row["id"],
        workspace_id=row["workspace_id"],
        agent_kind=row["agent_kind"],
        agent_version_id=row["agent_version_id"],
        name=row["name"],
        specialty=row["specialty"],
        definition_id=row["definition_id"],
        created_at=row["created_at"],
    )


def insert(
    conn: sqlite3.Connection, workspace_id: str, agent_id: str, kind: str, name: str, specialty: str, definition_id: int
) -> None:
    now = clock.now()
    conn.execute("INSERT INTO actors VALUES (?, 'agent', ?, ?)", (agent_id, workspace_id, now))
    conn.execute("INSERT INTO agents (id, workspace_id, agent_kind, created_at) VALUES (?, ?, ?, ?)",
                 (agent_id, workspace_id, kind, now))  # fmt: skip
    versioned.set_version(
        conn, "agent_versions", "agent_id", agent_id,
        {"name": name, "specialty": specialty, "definition_id": definition_id},
    )  # fmt: skip


def get(conn: sqlite3.Connection, workspace_id: str, agent_id: str) -> AgentRow | None:
    """A live agent of this workspace, or None."""
    row = conn.execute("SELECT * FROM v_agents WHERE workspace_id = ? AND id = ?", (workspace_id, agent_id)).fetchone()
    return _row(row) if row is not None else None


def list(conn: sqlite3.Connection, workspace_id: str, kind: str | None = None) -> builtins.list[AgentRow]:
    sql = "SELECT v.* FROM v_agents v JOIN agents a ON a.id = v.id WHERE v.workspace_id = ?"
    args: builtins.list[str] = [workspace_id]
    if kind is not None:
        sql += " AND v.agent_kind = ?"
        args.append(kind)
    return [_row(r) for r in conn.execute(sql + " ORDER BY v.created_at, a.rowid", args)]


def builtin(conn: sqlite3.Connection, workspace_id: str, kind: str) -> AgentRow:
    """The workspace's one orchestrator, verifier or chat agent."""
    [agent] = list(conn, workspace_id, kind)
    return agent


def set_version(conn: sqlite3.Connection, agent: AgentRow, *, name: str | None = None) -> None:
    versioned.set_version(
        conn, "agent_versions", "agent_id", agent.id,
        {"name": name if name is not None else agent.name, "specialty": agent.specialty,
         "definition_id": agent.definition_id},
    )  # fmt: skip


def soft_delete(conn: sqlite3.Connection, agent_id: str) -> None:
    conn.execute("UPDATE agents SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (clock.now(), agent_id))


def last_name(conn: sqlite3.Connection, agent_id: str) -> str | None:
    """The agent's name, also for a deleted agent."""
    row = conn.execute(
        "SELECT name FROM agent_versions WHERE agent_id = ? ORDER BY version DESC LIMIT 1", (agent_id,)
    ).fetchone()
    return row["name"] if row is not None else None
