"""Mapping rules between the database and the wire (03-contract.md section 2)."""

import sqlite3

from twyf.contract.models import ORCHESTRATOR, USER, VERIFIER


def actor_to_wire(conn: sqlite3.Connection, workspace_id: str, actor_id: str) -> str:
    """The workspace's orchestrator is `orchestrator`, its verifier `verifier`, the user `user`. Others keep their id."""
    row = conn.execute(
        "SELECT a.actor_kind, g.agent_kind, g.workspace_id FROM actors a LEFT JOIN agents g ON g.id = a.id"
        " WHERE a.id = ?",
        (actor_id,),
    ).fetchone()
    if row is None:
        return actor_id
    if row["actor_kind"] == "user":
        return USER
    if row["workspace_id"] == workspace_id and row["agent_kind"] == "orchestrator":
        return ORCHESTRATOR
    if row["workspace_id"] == workspace_id and row["agent_kind"] == "verifier":
        return VERIFIER
    return actor_id
