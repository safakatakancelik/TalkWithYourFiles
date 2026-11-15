import importlib
import importlib.util
import os
import sqlite3
from typing import BinaryIO

from twyf.contract.models import FileItem, FileText
from twyf.contract.operations import (
    AddFileVersionInput,
    DeleteFileInput,
    GetFileTextInput,
    ListFilesInput,
    UploadFileInput,
)
from twyf.db.connection import transaction
from twyf.db.repos import files as repo
from twyf.files import integrity, store
from twyf.files.types import file_type
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.workspaces import require


def _item(conn: sqlite3.Connection, row: sqlite3.Row) -> FileItem:
    return FileItem(
        id=row["id"],
        name=row["name"],
        type=row["file_type"],
        size_kb=max(1, round(row["size_bytes"] / 1024)),
        uploaded_at=repo.uploaded_at(conn, row["file_version_id"]),
        status=repo.status(conn, row["file_version_id"], row["availability"]),
        version=row["version"],
    )


def _live(conn: sqlite3.Connection, ws_id: str, file_id: str) -> sqlite3.Row:
    row = repo.get(conn, ws_id, file_id)
    if row is None:
        raise ServiceError("not_found", "No such file", {"file_id": file_id})
    return row


def _save(stream: BinaryIO) -> tuple[str, int, str, int]:
    settings = state.settings()
    sha, size, location = store.save(settings.data_dir, stream, settings.max_upload_mb * 1024 * 1024)
    return sha, size, str(location), os.stat(settings.data_dir / location).st_mtime_ns


def _submit_ingest(ctx: RequestContext, file_version_id: str) -> None:
    """Hands the version to the background jobs, once ingestion exists (task B13)."""
    if importlib.util.find_spec("twyf.files.ingest") is None:
        return
    ingest = importlib.import_module("twyf.files.ingest").ingest
    settings = state.settings()
    system = ctx.as_actor("system")
    state.jobs().submit(lambda: ingest(state.connect, system, settings, file_version_id))


def _duplicate(conn: sqlite3.Connection, ctx: RequestContext, row: sqlite3.Row) -> int:
    return record(
        conn, ctx, "file.upload_duplicate", workspace_id=row["workspace_id"], entity_type="file", entity_id=row["id"],
        payload={"file_version_id": row["file_version_id"], "name": row["name"]},
    )  # fmt: skip


def upload(
    ctx: RequestContext, input: UploadFileInput, *, name: str, stream: BinaryIO, file_id: str | None = None
) -> FileItem:
    """A new, separate file at version 1. The same name and bytes as a live file make nothing new."""
    name = require_text(name, "name")
    with state.db() as conn:
        require(conn, input.ws)
        sha, size, location, mtime = _save(stream)
        with transaction(conn):
            existing = repo.find_duplicate(conn, input.ws, name, sha)
            if existing is not None:
                _duplicate(conn, ctx, existing)
                return _item(conn, existing)
            fid = file_id or new_id("f")
            fvid = new_id("fv")
            repo.insert_file(conn, input.ws, fid)
            repo.add_version(
                conn, workspace_id=input.ws, file_id=fid, file_version_id=fvid, sha256=sha, name=name,
                file_type=file_type(name), size_bytes=size, location=location, mtime_ns=mtime,
            )  # fmt: skip
            event_id = record(
                conn, ctx, "file.uploaded", workspace_id=input.ws, entity_type="file", entity_id=fid,
                payload={"file_version_id": fvid, "name": name, "size_bytes": size, "sha256": sha},
            )  # fmt: skip
        _submit_ingest(ctx.caused_by(event_id), fvid)
        return _item(conn, _live(conn, input.ws, fid))


def add_version(ctx: RequestContext, input: AddFileVersionInput, *, name: str, stream: BinaryIO) -> FileItem:
    """The same file, changed: closes its current version and adds the next. Its notes stay with it."""
    name = require_text(name, "name")
    with state.db() as conn:
        require(conn, input.ws)
        _live(conn, input.ws, input.file_id)
        sha, size, location, mtime = _save(stream)
        with transaction(conn):
            current = _live(conn, input.ws, input.file_id)
            if current["content_sha256"] == sha:
                _duplicate(conn, ctx, current)
                return _item(conn, current)
            fvid = new_id("fv")
            repo.add_version(
                conn, workspace_id=input.ws, file_id=input.file_id, file_version_id=fvid, sha256=sha, name=name,
                file_type=file_type(name), size_bytes=size, location=location, mtime_ns=mtime,
            )  # fmt: skip
            event_id = record(
                conn, ctx, "file.version_added", workspace_id=input.ws, entity_type="file", entity_id=input.file_id,
                payload={"file_version_id": fvid, "version": current["version"] + 1, "name": name,
                         "size_bytes": size, "sha256": sha},
            )  # fmt: skip
        _submit_ingest(ctx.caused_by(event_id), fvid)
        return _item(conn, _live(conn, input.ws, input.file_id))


def list(ctx: RequestContext, input: ListFilesInput) -> list[FileItem]:
    with state.db() as conn:
        require(conn, input.ws)
        integrity.verify_workspace(conn, ctx, input.ws)
        return [_item(conn, row) for row in repo.list(conn, input.ws)]


def delete(ctx: RequestContext, input: DeleteFileInput) -> None:
    """Hides the file and its notes. The stored content is not touched."""
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        _live(conn, input.ws, input.file_id)
        repo.soft_delete(conn, input.file_id)
        record(conn, ctx, "file.deleted", workspace_id=input.ws, entity_type="file", entity_id=input.file_id)


def get_text(ctx: RequestContext, input: GetFileTextInput) -> FileText:
    raise ServiceError("internal", "not implemented")
