import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillVersion:
    id: int
    slug: str
    version: int
    content_sha256: str
    body: str


@dataclass(frozen=True)
class DefinitionVersion:
    id: int
    definition_id: int
    slug: str
    kind: str
    version: int
    content_sha256: str
    frontmatter: dict[str, str]
    body: str
    config: dict[str, Any]
    resolved_prompt: str
    parent_version_id: int | None
    skills: list[SkillVersion]  # in the order of the definition's effective skill list


def definition_id(conn: sqlite3.Connection, slug: str, kind: str) -> int:
    """The id of the definition named `slug`, inserting it when new."""
    row = conn.execute("SELECT id FROM agent_definitions WHERE slug = ?", (slug,)).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute("INSERT INTO agent_definitions (slug, agent_kind) VALUES (?, ?)", (slug, kind))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def skill_id(conn: sqlite3.Connection, slug: str) -> int:
    row = conn.execute("SELECT id FROM skills WHERE slug = ?", (slug,)).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute("INSERT INTO skills (slug) VALUES (?)", (slug,))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def current_skill(conn: sqlite3.Connection, slug: str) -> SkillVersion | None:
    row = conn.execute(
        "SELECT v.*, s.slug FROM skill_versions v JOIN skills s ON s.id = v.skill_id"
        " WHERE s.slug = ? AND v.valid_to IS NULL",
        (slug,),
    ).fetchone()
    return _skill(row) if row is not None else None


def _skill(row: sqlite3.Row) -> SkillVersion:
    return SkillVersion(row["id"], row["slug"], row["version"], row["content_sha256"], row["body"])


def link_skills(conn: sqlite3.Connection, definition_version_id: int, skill_version_ids: list[int]) -> None:
    conn.executemany(
        "INSERT INTO agent_definition_version_skills (definition_version_id, skill_version_id) VALUES (?, ?)",
        [(definition_version_id, sid) for sid in skill_version_ids],
    )


def get_version(conn: sqlite3.Connection, version_id: int) -> DefinitionVersion:
    row = conn.execute(
        "SELECT v.*, d.slug, d.agent_kind FROM agent_definition_versions v"
        " JOIN agent_definitions d ON d.id = v.definition_id WHERE v.id = ?",
        (version_id,),
    ).fetchone()
    config: dict[str, Any] = json.loads(row["config"])
    skill_rows = conn.execute(
        "SELECT sv.*, s.slug FROM agent_definition_version_skills l"
        " JOIN skill_versions sv ON sv.id = l.skill_version_id JOIN skills s ON s.id = sv.skill_id"
        " WHERE l.definition_version_id = ? ORDER BY l.rowid",
        (version_id,),
    ).fetchall()
    skills = [_skill(r) for r in skill_rows]
    return DefinitionVersion(
        id=row["id"],
        definition_id=row["definition_id"],
        slug=row["slug"],
        kind=row["agent_kind"],
        version=row["version"],
        content_sha256=row["content_sha256"],
        frontmatter=json.loads(row["frontmatter"]),
        body=row["body"],
        config=config,
        resolved_prompt=row["resolved_prompt"],
        parent_version_id=row["parent_version_id"],
        skills=skills,
    )


def current_version_id(conn: sqlite3.Connection, definition_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM agent_definition_versions WHERE definition_id = ? AND valid_to IS NULL", (definition_id,)
    ).fetchone()
    return row["id"] if row is not None else None


def current_definitions(conn: sqlite3.Connection, kind: str) -> list[DefinitionVersion]:
    rows = conn.execute(
        "SELECT v.id FROM agent_definition_versions v JOIN agent_definitions d ON d.id = v.definition_id"
        " WHERE d.agent_kind = ? AND v.valid_to IS NULL ORDER BY d.slug",
        (kind,),
    ).fetchall()
    return [get_version(conn, r["id"]) for r in rows]
