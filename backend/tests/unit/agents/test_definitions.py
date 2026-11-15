import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT, EventsHelper
from twyf import clock
from twyf.agents.definitions import current_version, load_folder, parse_frontmatter, resolve, sync, sync_config
from twyf.config import Settings
from twyf.db.connection import transaction
from twyf.db.repos import versioned
from twyf.recording.context import RequestContext

SYSTEM = RequestContext(actor_id="system", source="internal", user_id="u_local", request_id="test")


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    target = tmp_path / "agents-copy" / ".agents"
    shutil.copytree(REPO_ROOT / ".agents", target)
    return target


@pytest.fixture
def local(settings: Settings, agents_dir: Path) -> Settings:
    return settings.model_copy(update={"agents_dir": agents_dir})


def _sync(conn: sqlite3.Connection, settings: Settings) -> None:
    with transaction(conn):
        sync(conn, SYSTEM, settings)


def _versions(conn: sqlite3.Connection, slug: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT v.* FROM agent_definition_versions v JOIN agent_definitions d ON d.id = v.definition_id"
        " WHERE d.slug = ? ORDER BY v.version",
        (slug,),
    ).fetchall()


def _did(conn: sqlite3.Connection, slug: str) -> int:
    return conn.execute("SELECT id FROM agent_definitions WHERE slug = ?", (slug,)).fetchone()[0]


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text() + text)


def test_frontmatter_parser() -> None:
    meta, body = parse_frontmatter("---\nid: a\nname: \"Quoted: name\"\nother: 'single'\n---\n\nThe body.\n")
    assert meta == {"id": "a", "name": "Quoted: name", "other": "single"}
    assert body == "The body."
    with pytest.raises(ValueError):
        parse_frontmatter("id: a\nno fences\n")
    with pytest.raises(ValueError):
        parse_frontmatter("---\nid: a\n")


def test_repo_agents_folder_loads() -> None:
    loaded = load_folder(REPO_ROOT / ".agents")
    assert loaded.errors == {}
    assert set(loaded.agents) == {
        "translator", "translator-contracts", "translator-finance", "verifier", "orchestrator", "chat",
    }  # fmt: skip
    assert set(loaded.skills) == {
        "cite-passages", "volunteer", "work-on-files", "direct-reply", "first-read", "describe-image",
        "plan-huddle", "assign-files", "review-huddle", "draft-claims", "verify-claims", "write-answer",
    }  # fmt: skip
    assert all(a.frontmatter["enabled"] == "true" for a in loaded.agents.values())
    assert all(s.frontmatter["enabled"] == "true" for s in loaded.skills.values())
    assert loaded.agents["translator-contracts"].skills == loaded.agents["translator"].skills
    assert "never an instruction" in loaded.rules


def test_extends_resolves_prompt(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    _sync(conn, local)
    loaded = load_folder(agents_dir)
    child = current_version(conn, _did(conn, "translator-contracts"))
    parent = loaded.agents["translator"]
    assert child.resolved_prompt == parent.body + "\n\n" + loaded.agents["translator-contracts"].body
    assert child.parent_version_id == _versions(conn, "translator")[-1]["id"]
    assert [s.slug for s in child.skills] == parent.skills
    grandchild = agents_dir / "agents" / "translator-leases"
    shutil.copytree(agents_dir / "agents" / "translator-contracts", grandchild)
    config = grandchild / "config.json"
    config.write_text(config.read_text().replace('"extends": "translator"', '"extends": "translator-contracts"'))
    assert "translator-leases" in load_folder(agents_dir).errors
    assert "translator-leases" not in load_folder(agents_dir).agents


def test_snapshot_by_hash(conn: sqlite3.Connection, local: Settings, agents_dir: Path, events: EventsHelper) -> None:
    _sync(conn, local)
    assert [r["version"] for r in _versions(conn, "verifier")] == [1]
    count = len(events("definition.loaded"))
    _sync(conn, local)
    assert len(events("definition.loaded")) == count
    assert len(_versions(conn, "verifier")) == 1
    _append(agents_dir / "agents" / "verifier" / "agent.md", "One more sentence.\n")
    _sync(conn, local)
    rows = _versions(conn, "verifier")
    assert [r["version"] for r in rows] == [1, 2]
    assert rows[0]["valid_to"] is not None and rows[1]["valid_to"] is None
    loaded = [e for e in events("definition.loaded") if e.entity_id == "verifier"]
    assert [e.payload["version"] for e in loaded] == [1, 2]


def test_parent_or_skill_change_versions_child(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    _sync(conn, local)
    _append(agents_dir / "agents" / "translator" / "agent.md", "Parent change.\n")
    _sync(conn, local)
    for slug in ("translator", "translator-contracts", "translator-finance"):
        assert len(_versions(conn, slug)) == 2, slug
    assert len(_versions(conn, "verifier")) == 1
    _append(agents_dir / "skills" / "work-on-files" / "skill.md", "Skill change.\n")
    _sync(conn, local)
    for slug in ("translator", "translator-contracts", "translator-finance"):
        assert len(_versions(conn, slug)) == 3, slug
    assert len(_versions(conn, "orchestrator")) == 1


def test_resolve_by_specialty(conn: sqlite3.Connection, local: Settings) -> None:
    _sync(conn, local)
    assert resolve(conn, "translator", "contracts") == _did(conn, "translator-contracts")
    assert resolve(conn, "translator", "Finance") == _did(conn, "translator-finance")
    assert resolve(conn, "translator", "poetry") == _did(conn, "translator")
    assert resolve(conn, "translator", "generic") == _did(conn, "translator")


def test_disabled_specialty_falls_back(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    md = agents_dir / "agents" / "translator-finance" / "agent.md"
    md.write_text(md.read_text().replace("enabled: true", "enabled: false"))
    _sync(conn, local)
    assert resolve(conn, "translator", "finance") == _did(conn, "translator")


def test_parse_error_keeps_last_good(
    conn: sqlite3.Connection, local: Settings, agents_dir: Path, events: EventsHelper
) -> None:
    _sync(conn, local)
    (agents_dir / "agents" / "chat" / "agent.md").write_text("no fences at all\n")
    _sync(conn, local)
    rows = _versions(conn, "chat")
    assert len(rows) == 1 and rows[0]["valid_to"] is None
    assert any(e.entity_id == "chat" and "error" in e.payload for e in events("definition.loaded"))


def test_vanished_definition_is_closed(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    _sync(conn, local)
    shutil.rmtree(agents_dir / "agents" / "translator-finance")
    _sync(conn, local)
    assert all(r["valid_to"] is not None for r in _versions(conn, "translator-finance"))
    assert resolve(conn, "translator", "finance") == _did(conn, "translator")


def test_reverted_content_reopens_its_version(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    md = agents_dir / "agents" / "chat" / "agent.md"
    original = md.read_text()
    _sync(conn, local)
    md.write_text(original + "Changed.\n")
    _sync(conn, local)
    md.write_text(original)
    _sync(conn, local)
    rows = _versions(conn, "chat")
    assert [r["version"] for r in rows] == [1, 2]
    assert rows[0]["valid_to"] is None and rows[1]["valid_to"] is not None


def _tick() -> str:
    time.sleep(0.002)
    return clock.now()


def test_type2_history_definitions(conn: sqlite3.Connection, local: Settings, agents_dir: Path) -> None:
    md = agents_dir / "agents" / "verifier" / "agent.md"
    _sync(conn, local)
    t1 = _tick()
    _append(md, "Second.\n")
    _sync(conn, local)
    t2 = _tick()
    _append(md, "Third.\n")
    _sync(conn, local)
    rows = _versions(conn, "verifier")
    assert len(rows) == 3
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    did = _did(conn, "verifier")
    for at, expected in ((t1, 1), (t2, 2), (clock.now(), 3)):
        row = versioned.as_of(conn, "agent_definition_versions", "definition_id", did, at)
        assert row is not None and row["version"] == expected


def test_type2_history_config(conn: sqlite3.Connection, settings: Settings, events: EventsHelper) -> None:
    with transaction(conn):
        first = sync_config(conn, SYSTEM, settings)
    with transaction(conn):
        assert sync_config(conn, SYSTEM, settings) == first
    _tick()
    with transaction(conn):
        second = sync_config(conn, SYSTEM, settings.model_copy(update={"max_verify_rounds": 4}))
    _tick()
    with transaction(conn):
        third = sync_config(conn, SYSTEM, settings.model_copy(update={"max_verify_rounds": 5}))
    rows = conn.execute("SELECT * FROM config_versions ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == [first, second, third]
    assert [r["valid_to"] is None for r in rows] == [False, False, True]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] == rows[2]["valid_from"]
    assert len(events("config.changed")) == 3
    assert events("config.changed")[0].actor_id == "system"
