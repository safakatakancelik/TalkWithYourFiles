"""The only way a citation comes into being: a quote found, character for character, in the file's text."""

import re
import sqlite3
from contextlib import nullcontext

from twyf import clock
from twyf.citations.check import check_row
from twyf.citations.normalize import normalize
from twyf.db.connection import transaction
from twyf.db.repos import citations
from twyf.db.repos.citations import CitationRow
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

MIN_QUOTE = 8
MAX_QUOTE = 600
MAX_PASSAGE = 600
_SENTENCE_END = re.compile(r"[.?!](?=\s)")


class QuoteRejected(Exception):
    def __init__(self, reason: str, quote: str) -> None:
        super().__init__(f"{reason}: {quote!r}")
        self.reason = reason
        self.quote = quote


def _passage(text: str, block_start: int, block_end: int, start: int, end: int) -> tuple[int, int]:
    """The block, when short enough. Otherwise the quote widened to sentence ends, at most 600 characters."""
    if block_end - block_start <= MAX_PASSAGE:
        return block_start, block_end
    ends = [m.end() for m in _SENTENCE_END.finditer(text, block_start, block_end)]
    left = max([block_start] + [e + 1 for e in ends if e + 1 <= start])
    right = min([block_end] + [e for e in ends if e >= end])
    if right - left > MAX_PASSAGE:
        spare = MAX_PASSAGE - (end - start)
        left = max(left, start - spare // 2)
        right = min(right, left + MAX_PASSAGE)
        left = max(left, right - MAX_PASSAGE)
    return left, right


def _locate(
    conn: sqlite3.Connection, workspace_id: str, passage_id: str, q: str
) -> tuple[sqlite3.Row | None, int, str | None]:
    """The chunk, the quote's offset in the extraction text, and why it was rejected, if it was."""
    if len(q) < MIN_QUOTE:
        return None, -1, "too_short"
    if len(q) > MAX_QUOTE:
        return None, -1, "too_long"
    chunk_id = passage_id[1:] if passage_id.startswith("p") else ""
    chunk = conn.execute(
        "SELECT c.*, x.text AS extraction_text, x.file_version_id FROM chunks c"
        " JOIN extractions x ON x.id = c.extraction_id WHERE c.id = ? AND c.workspace_id = ?",
        (int(chunk_id) if chunk_id.isdigit() else -1, workspace_id),
    ).fetchone()
    if chunk is None:
        return None, -1, "unknown_passage"
    found = chunk["text"].find(q)
    start = chunk["char_start"] + found if found >= 0 else chunk["extraction_text"].find(q)
    if start < 0:
        return None, -1, "quote_not_found"
    return chunk, start, None


def create_citation(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    *,
    workspace_id: str,
    passage_id: str,
    quote: str,
    agent_id: str,
    turn_id: str | None,
) -> CitationRow:
    """Raises QuoteRejected(reason) and records citation.rejected. On success records citation.created.

    Joins the caller's transaction when there is one, else writes in its own."""
    q = normalize(quote)
    chunk, start, reason = _locate(conn, workspace_id, passage_id, q)
    scope = nullcontext(conn) if conn.in_transaction else transaction(conn)
    if chunk is None:
        with scope:
            record(
                conn, ctx, "citation.rejected", workspace_id=workspace_id, turn_id=turn_id,
                payload={"quote": quote, "passage_id": passage_id, "reason": reason},
            )  # fmt: skip
        raise QuoteRejected(reason or "quote_not_found", quote)
    text: str = chunk["extraction_text"]
    end = start + len(q)
    blocks = conn.execute(
        "SELECT * FROM blocks WHERE extraction_id = ? AND char_end > ? AND char_start < ? ORDER BY ordinal",
        (chunk["extraction_id"], start, end),
    ).fetchall()
    passage_start, passage_end = _passage(text, blocks[0]["char_start"], blocks[-1]["char_end"], start, end)
    row = CitationRow(
        id=new_id("c"), workspace_id=workspace_id, file_id=chunk["file_id"],
        file_version_id=chunk["file_version_id"], extraction_id=chunk["extraction_id"], char_start=start,
        char_end=end, quote=text[start:end], passage_start=passage_start, passage_end=passage_end,
        passage=text[passage_start:passage_end], location=blocks[0]["label"], found_by_agent_id=agent_id,
        turn_id=turn_id, created_at=clock.now(),
    )  # fmt: skip
    with scope:
        citations.insert(conn, row)
        result = check_row(conn, row)
        if not result.ok:  # pragma: no cover -- a located quote always passes; this guards the guarantee
            raise AssertionError(f"a new citation failed the mechanical check: {result.reason}")
        record(
            conn, ctx, "citation.created", workspace_id=workspace_id, turn_id=turn_id, entity_type="citation",
            entity_id=row.id, payload={"file_id": row.file_id, "file_version_id": row.file_version_id, "quote": row.quote},
        )  # fmt: skip
    return row
