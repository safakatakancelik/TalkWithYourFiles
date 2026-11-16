"""Loads `.agents` and snapshots it into the database, one version per content hash (02-data-model.md 7.4)."""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from twyf import clock
from twyf.config import Settings
from twyf.db.repos import definitions as repo
from twyf.db.repos import versioned
from twyf.db.repos.definitions import DefinitionVersion
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

log = logging.getLogger(__name__)

KINDS = ("translator", "verifier", "orchestrator", "chat")


@dataclass(frozen=True)
class LoadedSkill:
    slug: str
    frontmatter: dict[str, str]
    body: str
    source_path: Path
    content_sha256: str


@dataclass(frozen=True)
class LoadedAgent:
    slug: str
    kind: str
    frontmatter: dict[str, str]
    body: str
    config: dict[str, Any]
    extends: str | None
    specialty: str | None
    skills: list[str]  # the parent's list followed by this definition's additions
    source_path: Path
    content: bytes  # agent.md bytes followed by config.json bytes


@dataclass
class LoadedAgents:
    agents: dict[str, LoadedAgent]
    skills: dict[str, LoadedSkill]
    rules: str  # the body of agents.md
    errors: dict[str, str] = field(default_factory=dict[str, str])  # definition or skill slug -> why it was not loaded


@dataclass
class SyncResult:
    definition_version_ids: list[int] = field(default_factory=list[int])
    skill_version_ids: list[int] = field(default_factory=list[int])


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """`key: value` lines between `---` fences, then the body. Not YAML."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("no opening --- fence")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("no closing --- fence") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"not a key: value line: {line!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, "\n".join(lines[end + 1 :]).strip()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_agent(folder: Path) -> tuple[LoadedAgent, dict[str, Any]]:
    md, cfg = folder / "agent.md", folder / "config.json"
    md_bytes, cfg_bytes = md.read_bytes(), cfg.read_bytes()
    frontmatter, body = parse_frontmatter(md_bytes.decode())
    raw = json.loads(cfg_bytes)
    if not isinstance(raw, dict):
        raise TypeError("config.json is not an object")
    config = cast(dict[str, Any], raw)
    twyf = cast(dict[str, Any], config.get("twyf", {}))
    kind = twyf.get("kind")
    if kind not in KINDS:
        raise ValueError(f"twyf.kind must be one of {KINDS}")
    agent = LoadedAgent(
        slug=folder.name,
        kind=kind,
        frontmatter=frontmatter,
        body=body,
        config=config,
        extends=twyf.get("extends"),
        specialty=twyf.get("specialty"),
        skills=list(twyf.get("skills", [])),
        source_path=md,
        content=md_bytes + cfg_bytes,
    )
    return agent, twyf


def load_folder(path: Path) -> LoadedAgents:
    """Reads `.agents`. A definition or skill that fails to load is left out and named in `errors`."""
    _, rules = parse_frontmatter((path / "agents.md").read_text())
    loaded = LoadedAgents(agents={}, skills={}, rules=rules)
    for folder in sorted(p for p in (path / "skills").iterdir() if p.is_dir()):
        try:
            data = (folder / "skill.md").read_bytes()
            frontmatter, body = parse_frontmatter(data.decode())
            loaded.skills[folder.name] = LoadedSkill(folder.name, frontmatter, body, folder / "skill.md", _sha(data))
        except (OSError, ValueError) as error:
            loaded.errors[folder.name] = str(error)
    raw: dict[str, LoadedAgent] = {}
    for folder in sorted(p for p in (path / "agents").iterdir() if p.is_dir()):
        try:
            raw[folder.name], _ = _load_agent(folder)
        except (OSError, ValueError, TypeError) as error:
            loaded.errors[folder.name] = str(error)
    for slug, agent in raw.items():
        parent = raw.get(agent.extends) if agent.extends else None
        if agent.extends and parent is None:
            loaded.errors[slug] = f"extends unknown definition {agent.extends!r}"
            continue
        if parent is not None and parent.extends:
            loaded.errors[slug] = "a child of a child is not allowed: extends is one level only"
            continue
        if parent is not None and parent.kind != agent.kind:
            loaded.errors[slug] = "extends a definition of another kind"
            continue
        skills = (parent.skills if parent else []) + [s for s in agent.skills if not parent or s not in parent.skills]
        missing = [s for s in skills if s not in loaded.skills]
        if missing:
            loaded.errors[slug] = f"unknown skills: {missing}"
            continue
        loaded.agents[slug] = replace(agent, skills=skills)
    return loaded


def _put_version(
    conn: sqlite3.Connection, table: str, key_col: str, key: int, sha: str, values: dict[str, Any]
) -> tuple[int, str]:
    """Makes the row with this content hash current. Returns its id and 'same', 'new' or 'reopened'.

    The schema allows one row per (key, hash), so content that returns to an earlier hash reopens that row.
    The event recorded for it says `reopened`, so the log keeps every change in order.
    """
    rows = conn.execute(f"SELECT id, valid_to FROM {table} WHERE {key_col} = ? AND content_sha256 = ?", (key, sha))
    earlier = rows.fetchone()
    if earlier is not None and earlier["valid_to"] is None:
        return earlier["id"], "same"
    if earlier is not None:
        now = clock.now()
        conn.execute(f"UPDATE {table} SET valid_to = ? WHERE {key_col} = ? AND valid_to IS NULL", (now, key))
        conn.execute(f"UPDATE {table} SET valid_to = NULL WHERE id = ?", (earlier["id"],))
        return earlier["id"], "reopened"
    return versioned.set_version(conn, table, key_col, key, {"content_sha256": sha, **values}), "new"


def _version_no(conn: sqlite3.Connection, table: str, row_id: int) -> int:
    return conn.execute(f"SELECT version FROM {table} WHERE id = ?", (row_id,)).fetchone()[0]


def sync(conn: sqlite3.Connection, ctx: RequestContext, settings: Settings) -> SyncResult:
    """Snapshots `.agents` into the database. Run inside the caller's transaction."""
    loaded = load_folder(settings.agents_dir)
    result = SyncResult()
    for slug, error in loaded.errors.items():
        log.error("agent definition %s not loaded: %s", slug, error)
        record(conn, ctx, "definition.loaded", entity_type="definition", entity_id=slug, payload={"error": error})
    skill_versions: dict[str, int] = {}
    for slug, skill in loaded.skills.items():
        values = {
            "frontmatter": json.dumps(skill.frontmatter),
            "body": skill.body,
            "source_path": str(skill.source_path),
        }
        vid, outcome = _put_version(
            conn, "skill_versions", "skill_id", repo.skill_id(conn, slug), skill.content_sha256, values
        )
        skill_versions[slug] = vid
        if outcome != "same":
            result.skill_version_ids.append(vid)
            version = _version_no(conn, "skill_versions", vid)
            record(
                conn,
                ctx,
                "skill.loaded",
                entity_type="skill",
                entity_id=slug,
                payload={"slug": slug, "version": version, "reopened": outcome == "reopened"},
            )
    hashes: dict[str, str] = {}
    version_ids: dict[str, int] = {}
    ordered = sorted(loaded.agents.values(), key=lambda a: (a.extends is not None, a.slug))
    for agent in ordered:
        parent = loaded.agents[agent.extends] if agent.extends else None
        parent_hash = hashes[parent.slug] if parent else ""
        skill_hashes = sorted(loaded.skills[s].content_sha256 for s in agent.skills)
        sha = _sha(agent.content + parent_hash.encode() + "".join(skill_hashes).encode())
        hashes[agent.slug] = sha
        resolved = f"{parent.body}\n\n{agent.body}" if parent else agent.body
        values = {
            "frontmatter": json.dumps(agent.frontmatter),
            "body": agent.body,
            "config": json.dumps(agent.config, sort_keys=True),
            "resolved_prompt": resolved,
            "parent_version_id": version_ids[parent.slug] if parent else None,
            "source_path": str(agent.source_path),
        }
        did = repo.definition_id(conn, agent.slug, agent.kind)
        vid, outcome = _put_version(conn, "agent_definition_versions", "definition_id", did, sha, values)
        version_ids[agent.slug] = vid
        if outcome != "same":
            existing = {r[0] for r in conn.execute(
                "SELECT skill_version_id FROM agent_definition_version_skills WHERE definition_version_id = ?", (vid,)
            )}  # fmt: skip
            repo.link_skills(conn, vid, [skill_versions[s] for s in agent.skills if skill_versions[s] not in existing])
            result.definition_version_ids.append(vid)
            version = _version_no(conn, "agent_definition_versions", vid)
            record(
                conn, ctx, "definition.loaded", entity_type="definition", entity_id=agent.slug,
                payload={"slug": agent.slug, "version": version, "reopened": outcome == "reopened"},
                definition_version_id=vid,
            )  # fmt: skip
    _retire_vanished(conn, set(loaded.agents) | set(loaded.errors))
    return result


def _retire_vanished(conn: sqlite3.Connection, present: set[str]) -> None:
    """Closes definitions that left `.agents`. Agents that used one fall back to their kind's base definition."""
    now = clock.now()
    for row in conn.execute("SELECT id, slug FROM agent_definitions").fetchall():
        if row["slug"] not in present:
            conn.execute(
                "UPDATE agent_definition_versions SET valid_to = ? WHERE definition_id = ? AND valid_to IS NULL",
                (now, row["id"]),
            )
    orphans = conn.execute(
        "SELECT v.agent_id, v.name, v.specialty, a.agent_kind FROM agent_versions v JOIN agents a ON a.id = v.agent_id"
        " WHERE v.valid_to IS NULL AND NOT EXISTS (SELECT 1 FROM agent_definition_versions d"
        " WHERE d.definition_id = v.definition_id AND d.valid_to IS NULL)"
    ).fetchall()
    for orphan in orphans:
        base = conn.execute("SELECT id FROM agent_definitions WHERE slug = ?", (orphan["agent_kind"],)).fetchone()
        if base is None:
            continue
        versioned.set_version(
            conn, "agent_versions", "agent_id", orphan["agent_id"],
            {"name": orphan["name"], "specialty": orphan["specialty"], "definition_id": base["id"]},
        )  # fmt: skip


def resolve(conn: sqlite3.Connection, kind: str, specialty: str) -> int:
    """The definition for a new agent: the enabled one of this kind serving the speciality, else the kind's base."""
    base: int | None = None
    for definition in repo.current_definitions(conn, kind):
        twyf = cast(dict[str, Any], definition.config.get("twyf", {}))
        enabled = definition.frontmatter.get("enabled", "true").lower() == "true"
        served = twyf.get("specialty")
        if enabled and isinstance(served, str) and served.lower() == specialty.lower():
            return definition.definition_id
        if definition.slug == kind:
            base = definition.definition_id
    if base is None:
        raise LookupError(f"no base definition for kind {kind!r}")
    return base


def current_version(conn: sqlite3.Connection, definition_id: int) -> DefinitionVersion:
    vid = repo.current_version_id(conn, definition_id)
    if vid is None:
        raise LookupError(f"definition {definition_id} has no current version")
    return repo.get_version(conn, vid)


def sync_config(conn: sqlite3.Connection, ctx: RequestContext, settings: Settings) -> int:
    """Snapshots the behaviour settings. Returns the current config_versions id."""
    config = settings.behaviour_json()
    sha = _sha(config.encode())
    row = conn.execute("SELECT id, valid_to FROM config_versions WHERE content_sha256 = ?", (sha,)).fetchone()
    if row is not None and row["valid_to"] is None:
        return row["id"]
    now = clock.now()
    conn.execute("UPDATE config_versions SET valid_to = ? WHERE valid_to IS NULL", (now,))
    reopened = row is not None
    if row is not None:
        conn.execute("UPDATE config_versions SET valid_to = NULL WHERE id = ?", (row["id"],))
        config_id: int = row["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO config_versions (content_sha256, config, valid_from) VALUES (?, ?, ?)", (sha, config, now)
        )
        assert cursor.lastrowid is not None
        config_id = cursor.lastrowid
    record(conn, ctx, "config.changed", payload={"config": json.loads(config), "reopened": reopened},
           config_version_id=config_id)  # fmt: skip
    return config_id
