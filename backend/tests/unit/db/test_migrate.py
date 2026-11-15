import shutil
import sqlite3
from pathlib import Path

import pytest

from twyf.db import migrate as migrate_module
from twyf.db.connection import connect, transaction
from twyf.db.migrate import migrate

LOOKUPS: dict[str, set[str]] = {
    "sources": {"ui", "api", "mcp", "cli", "internal"},
    "actor_kinds": {"user", "agent", "system"},
    "agent_kinds": {"translator", "verifier", "orchestrator", "chat"},
    "note_kinds": {"summary", "finding", "interpretation"},
    "weights": {"off", "low", "normal", "high"},
    "file_types": {"pdf", "docx", "csv", "md", "txt", "image", "other"},
    "location_kinds": {"store", "path", "remote"},
    "availability_states": {"ok", "missing", "changed"},
    "extraction_kinds": {"text", "ocr", "description"},
    "claim_kinds": {"quoted", "derived"},
    "verdict_kinds": {"supported", "partly_supported", "unsupported", "mechanical_fail"},
    "question_states": {
        "received", "planning", "broadcasting", "assigning", "working", "reviewing", "drafting",
        "verifying", "writing", "answered", "answered_partial", "failed", "cancelled", "interrupted",
    },
    "turn_states": {"queued", "claimed", "done", "failed", "timed_out", "cancelled"},
    "turn_types": {
        "plan", "assign", "review", "draft_claims", "volunteer", "work", "direct_reply",
        "first_read", "describe_image", "verify", "write_answer",
    },
}  # fmt: skip

EVENT_TYPES = {
    "server.started", "definition.loaded", "skill.loaded", "config.changed",
    "workspace.created", "workspace.renamed", "workspace.deleted",
    "file.uploaded", "file.version_added", "file.upload_duplicate", "file.ingest_started",
    "file.extraction_completed", "file.extraction_failed", "file.indexed", "file.missing", "file.changed",
    "file.restored", "file.deleted",
    "agent.created", "agent.renamed", "agent.deleted",
    "note.created", "note.edited", "note.deleted", "note.weight_set",
    "session.created", "session.renamed", "session.deleted", "message.created",
    "question.asked", "question.status", "question.state_changed",
    "huddle.round_started", "huddle.broadcast", "huddle.member_joined", "huddle.file_assigned", "huddle.reading",
    "retrieval.searched", "citation.created", "citation.rejected", "huddle.statement",
    "claims.drafted", "verification.started", "verification.completed", "huddle.reopened", "huddle.member_left",
    "context.extended", "answer.written", "question.completed", "question.failed", "question.cancelled",
    "question.interrupted",
    "turn.queued", "turn.claimed", "turn.completed", "turn.failed", "turn.timed_out", "turn.cancelled",
    "runtime.waiting", "translator.asked", "translator.replied", "demo.seeded",
}  # fmt: skip


def _dump(path: Path) -> list[str]:
    c = sqlite3.connect(path)
    try:
        return list(c.iterdump())
    finally:
        c.close()


def test_migrate_fresh(db_path: Path) -> None:
    assert migrate(db_path) == [1]
    conn = connect(db_path)
    rows = conn.execute("SELECT version, name FROM schema_migrations").fetchall()
    assert [tuple(r) for r in rows] == [(1, "init")]
    assert not list(db_path.parent.glob("*.bak-*"))


def test_migrate_idempotent(db_path: Path) -> None:
    migrate(db_path)
    before = _dump(db_path)
    assert migrate(db_path) == []
    assert _dump(db_path) == before


def test_migrate_backs_up(db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    migrate(db_path)
    folder = tmp_path / "migrations"
    shutil.copytree(migrate_module.MIGRATIONS_DIR, folder)
    (folder / "0002_extra.sql").write_text("CREATE TABLE extra (id INTEGER PRIMARY KEY);\n")
    monkeypatch.setattr(migrate_module, "MIGRATIONS_DIR", folder)
    assert migrate(db_path) == [2]
    backup = db_path.with_name("twyf.db.bak-0002")
    assert backup.exists()
    old = sqlite3.connect(backup)
    assert [r[0] for r in old.execute("SELECT version FROM schema_migrations")] == [1]
    assert old.execute("SELECT 1 FROM sqlite_master WHERE name='extra'").fetchone() is None
    old.close()


def test_failed_migration_rolls_back(db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    migrate(db_path)
    folder = tmp_path / "migrations"
    shutil.copytree(migrate_module.MIGRATIONS_DIR, folder)
    (folder / "0002_bad.sql").write_text("CREATE TABLE half (id INTEGER);\nTHIS IS NOT SQL;\n")
    monkeypatch.setattr(migrate_module, "MIGRATIONS_DIR", folder)
    with pytest.raises(sqlite3.Error):
        migrate(db_path)
    conn = connect(db_path)
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='half'").fetchone() is None
    assert [r[0] for r in conn.execute("SELECT version FROM schema_migrations")] == [1]


def test_lookup_seeds(conn: sqlite3.Connection) -> None:
    for table, codes in LOOKUPS.items():
        assert {r[0] for r in conn.execute(f"SELECT code FROM {table}")} == codes, table
    assert {r[0] for r in conn.execute("SELECT code FROM event_types")} == EVENT_TYPES
    assert conn.execute("SELECT name FROM users WHERE id='u_local'").fetchone()[0] == "Local user"
    assert {r[0] for r in conn.execute("SELECT id FROM actors")} == {"u_local", "system"}


def test_app_events_append_only(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO app_events (occurred_at, event_type, actor_id, source, user_id) "
        "VALUES ('2026-11-15T00:00:00.000Z', 'server.started', 'system', 'internal', 'u_local')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE app_events SET source = 'api'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM app_events")


def test_foreign_keys_on(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO workspaces VALUES ('ws_1', 'u_local', '2026-11-15T00:00:00.000Z', NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO notes (id, workspace_id, file_id, file_version_id, author_id, kind, created_at) "
            "VALUES ('n_1', 'ws_1', 'f_missing', 'fv_missing', 'u_local', 'interpretation', '2026-11-15T00:00:00.000Z')"
        )


def test_connection_settings(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("SELECT vec_version()").fetchone()[0].startswith("v")


def test_transaction_commits_and_rolls_back(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO users VALUES ('u_2', 'Two', '2026-11-15T00:00:00.000Z')")
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO users VALUES ('u_3', 'Three', '2026-11-15T00:00:00.000Z')")
        raise RuntimeError("boom")
    assert {r[0] for r in conn.execute("SELECT id FROM users")} == {"u_local", "u_2"}
