import os
import sqlite3
from pathlib import Path

import pytest

from tests.conftest import EventsHelper, upload
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.files import integrity
from twyf.recording.context import RequestContext


def _version(conn: sqlite3.Connection, file_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM v_files WHERE id = ?", (file_id,)).fetchone()


def _path(settings: Settings, row: sqlite3.Row) -> Path:
    return settings.data_dir / row["location"]


def test_verify_ok_fast(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = upload(ctx, ws.id, "a.txt", b"some text")

    def no_hashing(path: Path) -> str:
        raise AssertionError("hashed")

    monkeypatch.setattr(integrity, "sha256_of", no_hashing)
    assert integrity.verify(conn, ctx, _version(conn, item.id)["file_version_id"]) == "ok"


def test_verify_missing(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "a.txt", b"some text")
    row = _version(conn, item.id)
    _path(settings, row).unlink()
    for _ in range(3):
        assert integrity.verify(conn, ctx, row["file_version_id"]) == "missing"
    assert _version(conn, item.id)["availability"] == "missing"
    [event] = events("file.missing")
    assert (event.actor_id, event.source, event.entity_id) == ("system", "internal", item.id)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM file_availability WHERE file_version_id = ?", (row["file_version_id"],)
        ).fetchone()[0]
        == 2
    )


def test_verify_changed(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "a.txt", b"some text")
    row = _version(conn, item.id)
    _path(settings, row).write_bytes(b"other bytes!")
    assert integrity.verify(conn, ctx, row["file_version_id"]) == "changed"
    assert len(events("file.changed")) == 1
    assert integrity.verify_workspace(conn, ctx, ws.id) == [(item.id, "changed")]


def test_verify_touched(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings) -> None:
    item = upload(ctx, ws.id, "a.txt", b"some text")
    row = _version(conn, item.id)
    path = _path(settings, row)
    new_mtime = row["mtime_ns"] + 5_000_000_000
    os.utime(path, ns=(new_mtime, new_mtime))
    assert integrity.verify(conn, ctx, row["file_version_id"]) == "ok"
    assert _version(conn, item.id)["mtime_ns"] == new_mtime


def test_verify_restored(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "a.txt", b"some text")
    row = _version(conn, item.id)
    path = _path(settings, row)
    path.unlink()
    integrity.verify(conn, ctx, row["file_version_id"])
    path.write_bytes(b"some text")
    assert integrity.verify(conn, ctx, row["file_version_id"]) == "ok"
    assert [e.payload["to"] for e in events() if e.event_type.startswith("file.") and "to" in e.payload] == [
        "missing",
        "ok",
    ]
    assert len(events("file.restored")) == 1
