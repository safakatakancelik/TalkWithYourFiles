"""The background pipeline: availability check, parse, extraction and blocks, chunks. Calls no model."""

import logging
import sqlite3
from collections.abc import Callable

from twyf.citations.normalize import normalize
from twyf.config import Settings
from twyf.db.connection import transaction
from twyf.db.repos import extractions
from twyf.db.repos import files as files_repo
from twyf.db.repos.extractions import BlockRow
from twyf.files import integrity
from twyf.files.chunker import BlockSpan, chunk
from twyf.files.parsers import pick_parser
from twyf.files.parsers.base import ParsedDocument
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]


def build_extraction(doc: ParsedDocument) -> tuple[str, list[BlockRow]]:
    """The canonical text (normalised blocks joined by newlines, empty ones dropped) and each block's offsets."""
    parts: list[str] = []
    rows: list[BlockRow] = []
    position = 0
    for block in doc.blocks:
        text = normalize(block.text)
        if not text:
            continue
        if parts:
            position += 1  # the "\n" between blocks
        rows.append(
            BlockRow(len(rows), block.kind, block.label, block.page, block.bbox, position, position + len(text))
        )
        parts.append(text)
        position += len(text)
    return "\n".join(parts), rows


def _event(conn: sqlite3.Connection, ctx: RequestContext, row: sqlite3.Row, event_type: str, **payload: object) -> int:
    return record(
        conn, ctx, event_type, workspace_id=row["workspace_id"], entity_type="file", entity_id=row["file_id"],
        payload={"file_version_id": row["id"], **payload},
    )  # fmt: skip


def _fail(
    conn: sqlite3.Connection, ctx: RequestContext, row: sqlite3.Row, parser: str, version: str, error: str
) -> None:
    with transaction(conn):
        if extractions.find(conn, row["id"], "text", parser, version) is None:
            extractions.insert(
                conn, workspace_id=row["workspace_id"], file_version_id=row["id"], kind="text", parser=parser,
                parser_version=version, error=error,
            )  # fmt: skip
        _event(conn, ctx, row, "file.extraction_failed", parser=parser, error=error)


def index_extraction(conn: sqlite3.Connection, ctx: RequestContext, extraction_id: str) -> list[int]:
    """Chunks an extraction into chunks and chunks_fts in one transaction, unless that was done already."""
    extraction = extractions.get(conn, extraction_id)
    assert extraction is not None
    if extractions.has_chunks(conn, extraction_id):
        return []
    version = files_repo.version(conn, extraction["file_version_id"])
    assert version is not None
    spans = [
        BlockSpan(b["char_start"], b["char_end"], extraction["text"][b["char_start"] : b["char_end"]])
        for b in extractions.blocks(conn, extraction_id)
    ]
    with transaction(conn):
        return extractions.insert_chunks(
            conn, workspace_id=extraction["workspace_id"], extraction_id=extraction_id, file_id=version["file_id"],
            chunks=chunk(spans),
        )  # fmt: skip


def ingest(conn_factory: ConnFactory, ctx: RequestContext, settings: Settings, file_version_id: str) -> None:
    conn = conn_factory()
    try:
        row = files_repo.version(conn, file_version_id)
        if row is None:
            return
        if integrity.verify(conn, ctx, file_version_id) != "ok":
            return
        with transaction(conn):
            _event(conn, ctx, row, "file.ingest_started")
        parser = pick_parser(settings, row["file_type"])
        if parser is None:
            _fail(conn, ctx, row, "none", "0", f"no parser reads files of type {row['file_type']}")
            return
        try:
            documents = parser.parse(settings.data_dir / row["location"], row["file_type"])
        except Exception as error:  # noqa: BLE001 -- a parser may raise anything on a damaged file
            log.warning("parsing %s failed: %s", file_version_id, error)
            _fail(conn, ctx, row, parser.name, parser.version, f"{type(error).__name__}: {error}")
            return
        extraction_ids: list[str] = []
        for doc in documents:
            existing = extractions.find(conn, file_version_id, doc.kind, parser.name, parser.version)
            if existing is not None:
                extraction_ids.append(existing)
                continue
            text, blocks = build_extraction(doc)
            with transaction(conn):
                extraction_id = extractions.insert(
                    conn, workspace_id=row["workspace_id"], file_version_id=file_version_id, kind=doc.kind,
                    parser=parser.name, parser_version=parser.version, text=text, blocks=blocks,
                )  # fmt: skip
                _event(
                    conn, ctx, row, "file.extraction_completed", extraction_id=extraction_id, parser=parser.name,
                    kind=doc.kind, blocks=len(blocks), chars=len(text),
                )  # fmt: skip
            extraction_ids.append(extraction_id)
        chunk_count = sum(len(index_extraction(conn, ctx, x)) for x in extraction_ids)
        with transaction(conn):
            _event(conn, ctx, row, "file.indexed", chunks=chunk_count)
    finally:
        conn.close()


def pending_ingestion(conn: sqlite3.Connection) -> list[str]:
    return extractions.pending_ingestion(conn)
