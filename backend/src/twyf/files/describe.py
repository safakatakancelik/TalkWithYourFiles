"""An image described in words by a vision-capable runtime, stored as an extraction of kind `description`."""

import asyncio
import logging
import mimetypes
import sqlite3
from collections.abc import Callable

from twyf.citations.normalize import normalize
from twyf.config import Settings
from twyf.contract.turns import DescribeImageInput, DescribeImageOutput
from twyf.db.connection import transaction
from twyf.db.repos import extractions
from twyf.db.repos import files as files_repo
from twyf.db.repos.extractions import BlockRow
from twyf.files.first_read import reader
from twyf.files.ingest import embed_extractions, index_extraction
from twyf.files.integrity import verify
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.runtime.base import Attachment
from twyf.runtime.runner import TurnFailed, TurnRunner

log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]
LABEL = "Image description (written by a model)"


async def describe_image(
    runner: TurnRunner, conn_factory: ConnFactory, ctx: RequestContext, file_version_id: str
) -> None:
    """Skipped unless the runtime has `vision`. Stores the description, then chunks and embeds it."""
    if "vision" not in runner.runtime.capabilities:
        return
    settings: Settings = runner.settings

    def prepare(conn: sqlite3.Connection) -> tuple[sqlite3.Row, str] | None:
        row = files_repo.version(conn, file_version_id)
        if row is None or row["file_type"] != "image" or verify(conn, ctx, file_version_id) != "ok":
            return None
        agent_id = reader(conn, row["workspace_id"])
        return (row, agent_id) if agent_id is not None else None

    def with_conn[T](fn: Callable[[sqlite3.Connection], T]) -> T:
        conn = conn_factory()
        try:
            return fn(conn)
        finally:
            conn.close()

    prepared = await asyncio.to_thread(with_conn, prepare)
    if prepared is None:
        return
    row, agent_id = prepared
    path = settings.data_dir / row["location"]
    media_type = mimetypes.guess_type(row["name"])[0] or "application/octet-stream"
    try:
        out, turn_id = await runner.run(
            ctx.as_actor(agent_id), agent_id=agent_id, turn_type="describe_image",
            input=DescribeImageInput(file_name=row["name"]), output_model=DescribeImageOutput,
            attachments=[Attachment(media_type=media_type, path=str(path))],
        )  # fmt: skip
    except TurnFailed as failed:
        log.warning("describing %s failed: %s", file_version_id, failed.reason)
        return

    def store(conn: sqlite3.Connection) -> None:
        text = normalize(out.description)
        if not text:
            return
        event = {"file_version_id": file_version_id}
        with transaction(conn):
            extraction_id = extractions.insert(
                conn, workspace_id=row["workspace_id"], file_version_id=file_version_id, kind="description",
                parser="vision", parser_version="1", text=text, turn_id=turn_id,
                blocks=[BlockRow(0, "image", LABEL, None, None, 0, len(text))],
            )  # fmt: skip
            record(conn, ctx, "file.extraction_completed", workspace_id=row["workspace_id"], entity_type="file",
                   entity_id=row["file_id"], turn_id=turn_id,
                   payload={**event, "extraction_id": extraction_id, "parser": "vision", "kind": "description"})  # fmt: skip
        chunks = index_extraction(conn, ctx, extraction_id)
        embed_extractions(conn, settings, [extraction_id])
        with transaction(conn):
            record(conn, ctx, "file.indexed", workspace_id=row["workspace_id"], entity_type="file",
                   entity_id=row["file_id"], payload={**event, "chunks": len(chunks)})  # fmt: skip

    await asyncio.to_thread(with_conn, store)
