"""The availability check: is the app's copy of a file version still where it should be, with its bytes?"""

import hashlib
import sqlite3
from pathlib import Path

from twyf.db.connection import transaction
from twyf.db.repos import files as repo
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state

_EVENTS = {"missing": "file.missing", "changed": "file.changed", "ok": "file.restored"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _check(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[str, int | None]:
    """The state of the copy and, when it was hashed and matched, its new modification time."""
    path = state.settings().data_dir / row["location"]
    if not path.is_file():
        return "missing", None
    stat = path.stat()
    if stat.st_size == row["size_bytes"] and stat.st_mtime_ns == row["mtime_ns"]:
        return "ok", None
    if sha256_of(path) == row["content_sha256"]:
        return "ok", stat.st_mtime_ns
    return "changed", None


def _apply(conn: sqlite3.Connection, ctx: RequestContext, row: sqlite3.Row, result: str, mtime: int | None) -> None:
    if mtime is not None:
        repo.set_mtime(conn, row["id"], mtime)
    if result != row["availability"]:
        repo.set_availability(conn, row["id"], result)
        record(
            conn, ctx.as_actor("system"), _EVENTS[result], workspace_id=row["workspace_id"], entity_type="file",
            entity_id=row["file_id"], payload={"file_version_id": row["id"], "from": row["availability"], "to": result},
        )  # fmt: skip


def verify(conn: sqlite3.Connection, ctx: RequestContext, file_version_id: str) -> str:
    """Returns ok, missing or changed, and records a change of state. Joins the caller's transaction if any."""
    row = repo.version(conn, file_version_id)
    if row is None:
        raise LookupError(f"no file version {file_version_id}")
    result, mtime = _check(conn, row)
    if mtime is None and result == row["availability"]:
        return result
    if conn.in_transaction:
        _apply(conn, ctx, row, result, mtime)
    else:
        with transaction(conn):
            _apply(conn, ctx, row, result, mtime)
    return result


def verify_workspace(conn: sqlite3.Connection, ctx: RequestContext, workspace_id: str) -> list[tuple[str, str]]:
    """Checks the current version of every live file. Returns (file id, state) for each that is not ok."""
    bad: list[tuple[str, str]] = []
    for row in repo.list(conn, workspace_id):
        result = verify(conn, ctx, row["file_version_id"])
        if result != "ok":
            bad.append((row["id"], result))
    return bad
