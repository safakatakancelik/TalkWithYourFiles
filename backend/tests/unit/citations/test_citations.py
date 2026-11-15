import dataclasses
import sqlite3

import pytest

from tests.conftest import EventsHelper, upload
from twyf.citations.check import check, check_row
from twyf.citations.locate import QuoteRejected, create_citation
from twyf.contract.models import Workspace
from twyf.db.connection import transaction
from twyf.db.repos import citations
from twyf.recording.context import RequestContext
from twyf.services import agents


def _agent(conn: sqlite3.Connection, ws: Workspace) -> str:
    return agents.builtin(conn, ws.id, "orchestrator").id


def _passages(conn: sqlite3.Connection, file_id: str) -> list[str]:
    return [f"p{r[0]}" for r in conn.execute("SELECT id FROM chunks WHERE file_id = ? ORDER BY ordinal", (file_id,))]


def _cite(
    conn: sqlite3.Connection, ctx: RequestContext, ws: Workspace, passage_id: str, quote: str
) -> citations.CitationRow:
    return create_citation(
        conn, ctx, workspace_id=ws.id, passage_id=passage_id, quote=quote, agent_id=_agent(conn, ws), turn_id=None
    )


def _text(conn: sqlite3.Connection, row: citations.CitationRow) -> str:
    return conn.execute("SELECT text FROM extractions WHERE id = ?", (row.extraction_id,)).fetchone()[0]


def test_create_citation_exact(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029. Rent rises by 8%.")
    [passage] = _passages(conn, item.id)
    row = _cite(conn, ctx, ws, passage, "ends on 30 June 2029")
    assert _text(conn, row)[row.char_start : row.char_end] == "ends on 30 June 2029" == row.quote
    assert (row.file_id, row.location, row.passage) == (
        item.id,
        "Paragraph 1",
        "The lease ends on 30 June 2029. Rent rises by 8%.",
    )
    assert check(conn, row.id).ok
    [created] = events("citation.created")
    assert created.entity_id == row.id


def test_create_citation_whitespace_and_quotes(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "memo.txt", "He said “stop now” and left – quickly.".encode())
    [passage] = _passages(conn, item.id)
    row = _cite(conn, ctx, ws, passage, 'said "stop\n   now" and left - quickly')
    assert row.quote == 'said "stop now" and left - quickly'


def test_create_citation_outside_chunk(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    text = "\n\n".join([f"Part {i} " + "filler " * 190 for i in range(3)] + ["The secret code is BLUE-42."])
    item = upload(ctx, ws.id, "long.txt", text.encode())
    passages = _passages(conn, item.id)
    assert len(passages) > 1
    row = _cite(conn, ctx, ws, passages[0], "The secret code is BLUE-42.")
    assert _text(conn, row)[row.char_start : row.char_end] == "The secret code is BLUE-42."


def test_create_citation_inside_a_transaction(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Payment is due in thirty days.")
    [passage] = _passages(conn, item.id)
    with transaction(conn):
        row = _cite(conn, ctx, ws, passage, "due in thirty days")
    assert citations.get(conn, row.id) is not None


def test_create_citation_rejects(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029.")
    [passage] = _passages(conn, item.id)
    cases = [
        ("The lease finishes in mid 2029", "quote_not_found", passage),
        ("lease", "too_short", passage),
        ("x" * 700, "too_long", passage),
        ("The lease ends on 30 June 2029.", "unknown_passage", "p999999"),
        ("The lease ends on 30 June 2029.", "unknown_passage", "chunk-1"),
    ]
    for quote, reason, pid in cases:
        with pytest.raises(QuoteRejected) as raised:
            _cite(conn, ctx, ws, pid, quote)
        assert raised.value.reason == reason
    assert [e.payload["reason"] for e in events("citation.rejected")] == [r for _, r, _ in cases]
    assert conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0] == 0


def test_passage_contains_quote(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    sentences = [f"Sentence number {i} says something about the lease terms." for i in range(30)]
    item = upload(ctx, ws.id, "long.txt", ("Short block here.\n\n" + " ".join(sentences)).encode())
    passages = _passages(conn, item.id)
    short = _cite(conn, ctx, ws, passages[0], "Short block here")
    assert short.passage == "Short block here."
    long = _cite(conn, ctx, ws, passages[-1], "Sentence number 17 says something")
    assert len(long.passage) <= 600 and long.quote in long.passage
    assert long.passage.startswith("Sentence number 17") and long.passage.endswith("lease terms.")
    assert check(conn, long.id).ok


def test_passage_of_one_long_sentence_is_clipped(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "run-on.txt", (" ".join(f"word{i}" for i in range(400)) + ".").encode())
    passage = _passages(conn, item.id)[0]
    row = _cite(conn, ctx, ws, passage, "word100 word101 word102")
    assert len(row.passage) <= 600 and row.quote in row.passage
    assert check(conn, row.id).ok


def test_check_passes_and_fails(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029. Rent rises by 8%.")
    other = upload(ctx, ws.id, "other.txt", b"Something else entirely here.")
    [passage] = _passages(conn, item.id)
    row = _cite(conn, ctx, ws, passage, "ends on 30 June 2029")
    assert check(conn, row.id).ok and check_row(conn, row).reason is None
    altered = {
        "extraction_missing_or_altered": dataclasses.replace(row, extraction_id="x_nope"),
        "quote_mismatch": dataclasses.replace(row, quote="ends on 31 June 2029"),
        "passage_mismatch": dataclasses.replace(row, passage="The lease ends."),
        "offsets_invalid": dataclasses.replace(
            row, passage_start=row.char_start + 1, passage="", passage_end=row.char_start + 1
        ),
        "ownership_mismatch": dataclasses.replace(row, file_id=other.id),
    }
    for reason, copy in altered.items():
        result = check_row(conn, copy)
        assert (result.ok, result.reason) == (False, reason)
    assert check_row(conn, dataclasses.replace(row, workspace_id="ws_other")).reason == "ownership_mismatch"
    assert check_row(conn, dataclasses.replace(row, file_version_id="fv_nope")).reason == "ownership_mismatch"
    assert check(conn, "c_nope").reason == "citation_missing"
    with transaction(conn):
        conn.execute("UPDATE extractions SET text_sha256 = 'damaged' WHERE id = ?", (row.extraction_id,))
    assert check(conn, row.id).reason == "extraction_missing_or_altered"


def test_offsets_invalid_when_passage_text_matches(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection
) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029. Rent rises by 8%.")
    [passage] = _passages(conn, item.id)
    row = _cite(conn, ctx, ws, passage, "Rent rises by 8%")
    text = _text(conn, row)
    copy = dataclasses.replace(row, passage_start=0, passage_end=10, passage=text[0:10])
    assert check_row(conn, copy).reason == "offsets_invalid"


def test_to_wire(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029.")
    [passage] = _passages(conn, item.id)
    row = _cite(conn, ctx, ws, passage, "ends on 30 June 2029")
    wire = citations.to_wire(conn, row.id, 3)
    assert (wire.n, wire.agent_id, wire.file_name, wire.file_version, wire.id) == (
        3,
        "orchestrator",
        "lease.txt",
        1,
        row.id,
    )
    assert (wire.start, wire.end, wire.quote, wire.page) == (row.char_start, row.char_end, row.quote, None)
    with pytest.raises(LookupError):
        citations.to_wire(conn, "c_nope", 1)
