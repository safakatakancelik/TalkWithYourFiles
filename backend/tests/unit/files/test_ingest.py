import shutil
import sqlite3
from pathlib import Path

from tests.conftest import EventsHelper, add_version, upload
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.operations import GetFileTextInput, ListFilesInput
from twyf.files.ingest import build_extraction, ingest, pending_ingestion
from twyf.files.parsers.base import ParsedBlock, ParsedDocument
from twyf.recording.context import RequestContext
from twyf.services import files, state

FIXTURES = Path(__file__).parents[2] / "fixtures" / "parsing"


def _fv(conn: sqlite3.Connection, file_id: str) -> str:
    return conn.execute("SELECT file_version_id FROM v_files WHERE id = ?", (file_id,)).fetchone()[0]


def test_canonical_text_offsets(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    for name in ("sample.txt", "sample.md", "sample.csv", "sample.pdf", "sample.docx"):
        item = upload(ctx, ws.id, name, (FIXTURES / name).read_bytes())
        assert item.status == "ready", name
        [extraction] = conn.execute("SELECT * FROM extractions WHERE file_version_id = ?", (_fv(conn, item.id),))
        text = extraction["text"]
        blocks = conn.execute("SELECT * FROM blocks WHERE extraction_id = ?", (extraction["id"],)).fetchall()
        assert blocks
        assert "\n".join(text[b["char_start"] : b["char_end"]] for b in blocks) == text
        for b in blocks:
            assert text[b["char_start"] : b["char_end"]].strip() == text[b["char_start"] : b["char_end"]]
            assert "  " not in text[b["char_start"] : b["char_end"]]
        for c in conn.execute("SELECT * FROM chunks WHERE extraction_id = ?", (extraction["id"],)):
            assert text[c["char_start"] : c["char_end"]] == c["text"]


def test_build_extraction_normalises_and_drops_empty() -> None:
    doc = ParsedDocument("text", [ParsedBlock("paragraph", "P1", "  “A”\n b "), ParsedBlock("paragraph", "P2", " \n ")])
    text, rows = build_extraction(doc)
    assert text == '"A" b'
    assert [(r.char_start, r.char_end, r.label) for r in rows] == [(0, 5, "P1")]


def test_parse_failure_marks_unreadable(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "corrupt.pdf", (FIXTURES / "corrupt.pdf").read_bytes())
    assert item.status == "unreadable"
    [extraction] = conn.execute("SELECT * FROM extractions WHERE file_version_id = ?", (_fv(conn, item.id),))
    assert extraction["status"] == "failed" and extraction["error"]
    assert len(events("file.extraction_failed")) == 1
    assert events("file.indexed") == []
    other = upload(ctx, ws.id, "table.xlsx", b"PK\x03\x04 not parsed")
    assert other.status == "unreadable"


def test_ingest_events_follow_upload(ws: Workspace, ctx: RequestContext, events: EventsHelper) -> None:
    upload(ctx, ws.id, "a.txt", b"Some words here.")
    [uploaded] = events("file.uploaded")
    for event_type in ("file.ingest_started", "file.extraction_completed", "file.indexed"):
        [event] = events(event_type)
        assert (event.actor_id, event.source, event.cause_event_id) == ("system", "internal", uploaded.id)


def test_unusable_file_hidden_from_agents(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    gone = upload(ctx, ws.id, "gone.txt", b"This file will go.")
    damaged = upload(ctx, ws.id, "damaged.txt", b"This file will change.")
    fine = upload(ctx, ws.id, "fine.txt", b"This file stays.")
    location = conn.execute("SELECT location FROM v_files WHERE id = ?", (gone.id,)).fetchone()[0]
    (settings.data_dir / location).unlink()
    location = conn.execute("SELECT location FROM v_files WHERE id = ?", (damaged.id,)).fetchone()[0]
    (settings.data_dir / location).write_bytes(b"Something else entirely.")
    statuses = {f.id: f.status for f in files.list(ctx, ListFilesInput(ws=ws.id))}
    assert statuses == {gone.id: "missing", damaged.id: "changed", fine.id: "ready"}
    usable = {r[0] for r in conn.execute("SELECT id FROM v_usable_files WHERE workspace_id = ?", (ws.id,))}
    assert usable == {fine.id}


def test_everything_points_at_its_version(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    item = upload(ctx, ws.id, "plan.txt", b"Version one text.")
    v1 = _fv(conn, item.id)
    v1_extractions = conn.execute("SELECT id FROM extractions WHERE file_version_id = ?", (v1,)).fetchall()
    add_version(ctx, ws.id, item.id, "plan.txt", b"Version two text.")
    v2 = _fv(conn, item.id)
    assert v2 != v1
    assert conn.execute("SELECT id FROM extractions WHERE file_version_id = ?", (v1,)).fetchall() == v1_extractions
    [x1] = v1_extractions
    [x2] = conn.execute("SELECT id FROM extractions WHERE file_version_id = ?", (v2,)).fetchall()
    assert (
        conn.execute("SELECT text FROM chunks WHERE extraction_id = ?", (x1["id"],)).fetchone()[0]
        == "Version one text."
    )
    assert (
        conn.execute("SELECT text FROM chunks WHERE extraction_id = ?", (x2["id"],)).fetchone()[0]
        == "Version two text."
    )


def test_get_text(ws: Workspace, ctx: RequestContext) -> None:
    item = upload(ctx, ws.id, "a.txt", b"Hello there.\n\nGeneral words.")
    whole = files.get_text(ctx, GetFileTextInput(ws=ws.id, file_id=item.id))
    assert (whole.text, whole.start, whole.end, whole.total) == ("Hello there.\nGeneral words.", 0, 27, 27)
    part = files.get_text(ctx, GetFileTextInput(ws=ws.id, file_id=item.id, start=6, end=500))
    assert (part.text, part.start, part.end) == ("there.\nGeneral words.", 6, 27)


def test_pending_ingestion_and_resume(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    class NoJobs:
        def submit(self, fn: object) -> None:
            return None

        def join(self) -> None:
            return None

    state.configure(settings, NoJobs())
    item = upload(ctx, ws.id, "later.txt", b"Ingested later.")
    assert item.status == "processing"
    fv = _fv(conn, item.id)
    assert pending_ingestion(conn) == [fv]
    ingest(state.connect, ctx.as_actor("system"), settings, fv)
    assert pending_ingestion(conn) == []
    assert files.list(ctx, ListFilesInput(ws=ws.id))[0].status == "ready"
    shutil.rmtree(settings.data_dir / "files")
    ingest(state.connect, ctx.as_actor("system"), settings, fv)
