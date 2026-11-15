import builtins
import re
import sqlite3

from twyf import clock

ENTITY_TYPES = frozenset({"person", "company", "date", "decision", "place", "other"})
MAX_LABEL = 60


def norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip().lower()


def find(conn: sqlite3.Connection, workspace_id: str, norm: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM entities WHERE workspace_id = ? AND norm_label = ?", (workspace_id, norm)
    ).fetchone()
    return row["id"] if row is not None else None


def insert(
    conn: sqlite3.Connection, *, entity_id: str, workspace_id: str, label: str, norm: str, entity_type: str
) -> None:
    conn.execute(
        "INSERT INTO entities (id, workspace_id, label, norm_label, entity_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (entity_id, workspace_id, label, norm, entity_type, clock.now()),
    )


def add_mention(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    entity_id: str,
    file_id: str,
    created_by: str,
    question_id: str | None,
    citation_id: str | None = None,
) -> bool:
    """True when this file did not mention this entity before."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO entity_mentions (workspace_id, entity_id, file_id, citation_id, question_id, created_by,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (workspace_id, entity_id, file_id, citation_id, question_id, created_by, clock.now()),
    )
    return cursor.rowcount == 1


def map_entities(conn: sqlite3.Connection, workspace_id: str) -> builtins.list[sqlite3.Row]:
    """Entities with at least one mention in a live file."""
    return conn.execute(
        "SELECT DISTINCT e.id, e.label, e.rowid FROM entities e JOIN entity_mentions m ON m.entity_id = e.id"
        " JOIN files f ON f.id = m.file_id AND f.deleted_at IS NULL"
        " WHERE e.workspace_id = ? AND e.deleted_at IS NULL ORDER BY e.rowid",
        (workspace_id,),
    ).fetchall()


def map_links(conn: sqlite3.Connection, workspace_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT m.file_id, m.entity_id FROM entity_mentions m JOIN files f ON f.id = m.file_id AND f.deleted_at IS NULL"
        " JOIN entities e ON e.id = m.entity_id AND e.deleted_at IS NULL WHERE m.workspace_id = ? ORDER BY m.id",
        (workspace_id,),
    ).fetchall()
