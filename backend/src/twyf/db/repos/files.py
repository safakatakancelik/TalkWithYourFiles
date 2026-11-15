import builtins
import sqlite3

from twyf import clock
from twyf.contract.models import FileStatus
from twyf.db.repos import versioned


def insert_file(conn: sqlite3.Connection, workspace_id: str, file_id: str) -> None:
    conn.execute(
        "INSERT INTO files (id, workspace_id, created_at) VALUES (?, ?, ?)", (file_id, workspace_id, clock.now())
    )


def add_version(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    file_id: str,
    file_version_id: str,
    sha256: str,
    name: str,
    file_type: str,
    size_bytes: int,
    location: str,
    mtime_ns: int,
) -> None:
    """Closes the file's current version, if any, and adds the next, available."""
    versioned.set_version(
        conn, "file_versions", "file_id", file_id,
        {"id": file_version_id, "workspace_id": workspace_id, "content_sha256": sha256, "name": name,
         "file_type": file_type, "size_bytes": size_bytes, "location_kind": "store", "location": location,
         "mtime_ns": mtime_ns},
    )  # fmt: skip
    set_availability(conn, file_version_id, "ok")


def set_availability(conn: sqlite3.Connection, file_version_id: str, state: str) -> None:
    versioned.set_version(conn, "file_availability", "file_version_id", file_version_id, {"state": state})


def get(conn: sqlite3.Connection, workspace_id: str, file_id: str) -> sqlite3.Row | None:
    """A live file of this workspace with its current version, or None."""
    return conn.execute("SELECT * FROM v_files WHERE workspace_id = ? AND id = ?", (workspace_id, file_id)).fetchone()


def list(conn: sqlite3.Connection, workspace_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT v.* FROM v_files v JOIN files f ON f.id = v.id WHERE v.workspace_id = ? ORDER BY v.created_at, f.rowid",
        (workspace_id,),
    ).fetchall()


def version(conn: sqlite3.Connection, file_version_id: str) -> sqlite3.Row | None:
    """Any version, current or not, with its current availability."""
    return conn.execute(
        "SELECT v.*, a.state AS availability FROM file_versions v"
        " JOIN file_availability a ON a.file_version_id = v.id AND a.valid_to IS NULL WHERE v.id = ?",
        (file_version_id,),
    ).fetchone()


def find_duplicate(conn: sqlite3.Connection, workspace_id: str, name: str, sha256: str) -> sqlite3.Row | None:
    """A live file with this name whose current version has these bytes."""
    return conn.execute(
        "SELECT * FROM v_files WHERE workspace_id = ? AND name = ? AND content_sha256 = ? LIMIT 1",
        (workspace_id, name, sha256),
    ).fetchone()


def set_mtime(conn: sqlite3.Connection, file_version_id: str, mtime_ns: int) -> None:
    conn.execute("UPDATE file_versions SET mtime_ns = ? WHERE id = ?", (mtime_ns, file_version_id))


def soft_delete(conn: sqlite3.Connection, file_id: str) -> None:
    conn.execute("UPDATE files SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (clock.now(), file_id))


def uploaded_at(conn: sqlite3.Connection, file_version_id: str) -> str:
    return conn.execute("SELECT valid_from FROM file_versions WHERE id = ?", (file_version_id,)).fetchone()[0]


def status(conn: sqlite3.Connection, file_version_id: str, availability: str) -> FileStatus:
    """missing or changed from the availability check; else ready once indexed, unreadable when no extraction
    succeeded, and processing until then."""
    if availability == "missing":
        return "missing"
    if availability == "changed":
        return "changed"
    indexed = conn.execute(
        "SELECT 1 FROM app_events WHERE event_type = 'file.indexed' AND entity_type = 'file'"
        " AND json_extract(payload, '$.file_version_id') = ? LIMIT 1",
        (file_version_id,),
    ).fetchone()
    if indexed is not None:
        return "ready"
    extractions = conn.execute(
        "SELECT COUNT(*), SUM(status = 'ok') FROM extractions WHERE file_version_id = ?", (file_version_id,)
    ).fetchone()
    if extractions[0] and not extractions[1]:
        return "unreadable"
    return "processing"
