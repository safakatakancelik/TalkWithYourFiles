import hashlib
import sqlite3
import time
from pathlib import Path

import pytest

from tests.conftest import EventsHelper, add_version, upload
from twyf import clock
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.operations import DeleteFileInput, DeleteWorkspaceInput, ListFilesInput
from twyf.db.repos import versioned
from twyf.recording.context import RequestContext
from twyf.services import files, workspaces
from twyf.services.errors import ServiceError


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_upload_cases(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    first = upload(ctx, ws.id, "a.txt", b"first bytes")
    assert (first.name, first.type, first.version, first.size_kb) == ("a.txt", "txt", 1, 1)
    again = upload(ctx, ws.id, "a.txt", b"first bytes")
    assert again.id == first.id
    assert _count(conn, "files") == 1
    assert len(events("file.upload_duplicate")) == 1
    other = upload(ctx, ws.id, "a.txt", b"different bytes")
    assert other.id != first.id and other.version == 1
    assert _count(conn, "files") == 2
    [uploaded, _] = events("file.uploaded")
    assert (uploaded.actor_id, uploaded.source, uploaded.entity_id) == ("u_local", "api", first.id)


def test_add_file_version(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    v1 = upload(ctx, ws.id, "plan.txt", b"version one")
    time.sleep(0.002)
    between = clock.now()
    time.sleep(0.002)
    v2 = add_version(ctx, ws.id, v1.id, "plan-v2.txt", b"version two")
    assert (v2.id, v2.version, v2.name) == (v1.id, 2, "plan-v2.txt")
    rows = conn.execute("SELECT * FROM file_versions WHERE file_id = ? ORDER BY version", (v1.id,)).fetchall()
    assert [r["name"] for r in rows] == ["plan.txt", "plan-v2.txt"]
    assert rows[0]["valid_to"] == rows[1]["valid_from"] and rows[1]["valid_to"] is None
    assert rows[0]["content_sha256"] != rows[1]["content_sha256"] and rows[0]["location"] != rows[1]["location"]
    same = add_version(ctx, ws.id, v1.id, "plan-v3.txt", b"version two")
    assert same.version == 2
    assert len(events("file.upload_duplicate")) == 1
    old = versioned.as_of(conn, "file_versions", "file_id", v1.id, between)
    assert old is not None and old["version"] == 1
    assert events("file.version_added")[0].payload["version"] == 2
    with pytest.raises(ServiceError) as raised:
        add_version(ctx, ws.id, "f_nope", "x.txt", b"x")
    assert raised.value.code == "not_found"


def test_list_and_delete(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"aaa")
    b = upload(ctx, ws.id, "../../etc/passwd.txt", b"bbb")
    listed = files.list(ctx, ListFilesInput(ws=ws.id))
    assert [f.id for f in listed] == [a.id, b.id]
    assert listed[1].name == "../../etc/passwd.txt"
    assert all(f.status == "ready" for f in listed)
    files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=a.id))
    assert [f.id for f in files.list(ctx, ListFilesInput(ws=ws.id))] == [b.id]
    assert conn.execute("SELECT deleted_at FROM files WHERE id = ?", (a.id,)).fetchone()[0] is not None
    with pytest.raises(ServiceError):
        files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=a.id))


def test_list_shows_missing(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings) -> None:
    item = upload(ctx, ws.id, "a.txt", b"aaa")
    location = conn.execute("SELECT location FROM v_files WHERE id = ?", (item.id,)).fetchone()[0]
    (settings.data_dir / location).unlink()
    [listed] = files.list(ctx, ListFilesInput(ws=ws.id))
    assert listed.status == "missing"


def _stored(settings: Settings) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in (settings.data_dir / "files").rglob("*") if p.is_file()}


def test_content_never_written(ws: Workspace, ctx: RequestContext, settings: Settings) -> None:
    item = upload(ctx, ws.id, "a.txt", b"one")
    add_version(ctx, ws.id, item.id, "a.txt", b"two")
    before = _stored(settings)
    assert {hashlib.sha256(b).hexdigest() for b in before.values()} == {
        hashlib.sha256(b"one").hexdigest(),
        hashlib.sha256(b"two").hexdigest(),
    }
    files.list(ctx, ListFilesInput(ws=ws.id))
    files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=item.id))
    workspaces.delete(ctx, DeleteWorkspaceInput(ws=ws.id))
    assert _stored(settings) == before
