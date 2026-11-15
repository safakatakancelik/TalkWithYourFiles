"""The mechanical check: a citation's quote and passage are exactly where it says, in the version it names."""

import hashlib
import sqlite3
from dataclasses import dataclass

from twyf.db.repos import citations
from twyf.db.repos.citations import CitationRow


@dataclass
class CheckResult:
    ok: bool
    reason: str | None


def check_row(conn: sqlite3.Connection, row: CitationRow) -> CheckResult:
    extraction = conn.execute("SELECT * FROM extractions WHERE id = ?", (row.extraction_id,)).fetchone()
    if extraction is None or hashlib.sha256(extraction["text"].encode()).hexdigest() != extraction["text_sha256"]:
        return CheckResult(False, "extraction_missing_or_altered")
    text: str = extraction["text"]
    if text[row.char_start : row.char_end] != row.quote:
        return CheckResult(False, "quote_mismatch")
    if text[row.passage_start : row.passage_end] != row.passage:
        return CheckResult(False, "passage_mismatch")
    if not (row.passage_start <= row.char_start < row.char_end <= row.passage_end):
        return CheckResult(False, "offsets_invalid")
    owner = conn.execute(
        "SELECT f.id AS file_id, f.workspace_id FROM file_versions v JOIN files f ON f.id = v.file_id WHERE v.id = ?",
        (row.file_version_id,),
    ).fetchone()
    if (
        extraction["file_version_id"] != row.file_version_id
        or owner is None
        or owner["file_id"] != row.file_id
        or owner["workspace_id"] != row.workspace_id
    ):
        return CheckResult(False, "ownership_mismatch")
    return CheckResult(True, None)


def check(conn: sqlite3.Connection, citation_id: str) -> CheckResult:
    row = citations.get(conn, citation_id)
    if row is None:
        return CheckResult(False, "citation_missing")
    return check_row(conn, row)
