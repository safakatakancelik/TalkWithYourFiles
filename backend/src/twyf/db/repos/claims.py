import builtins
import sqlite3
from dataclasses import dataclass

from twyf import clock


@dataclass(frozen=True)
class Carried:
    verdict_id: int
    verdict: str
    reason: str


@dataclass(frozen=True)
class ClaimRow:
    id: str
    ref: str
    ordinal: int
    kind: str
    text: str
    expression: str | None
    stated_result: float | None
    computed_result: float | None
    arithmetic_error: str | None  # set when the expression failed the arithmetic check
    content_sha256: str
    citation_ids: tuple[str, ...]  # quoted: its own; derived: the union of its inputs'
    input_ids: tuple[str, ...]
    carried: Carried | None  # the verdict of an identical claim verified earlier in this question


def insert(
    conn: sqlite3.Connection, *, workspace_id: str, question_id: str, round_id: str, turn_id: str, row: ClaimRow
) -> None:
    conn.execute(
        "INSERT INTO claims (id, workspace_id, question_id, round_id, ordinal, kind, text, expression, stated_result,"
        " computed_result, content_sha256, turn_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row.id, workspace_id, question_id, round_id, row.ordinal, row.kind, row.text, row.expression,
         row.stated_result, row.computed_result, row.content_sha256, turn_id, clock.now()),
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO claim_citations (claim_id, citation_id) VALUES (?, ?)", [(row.id, c) for c in row.citation_ids]
    )
    conn.executemany(
        "INSERT INTO claim_inputs (claim_id, input_claim_id) VALUES (?, ?)", [(row.id, c) for c in row.input_ids]
    )


def latest_verdict(conn: sqlite3.Connection, question_id: str, content_sha256: str) -> Carried | None:
    """The newest verdict given in this question to a claim with this content."""
    row = conn.execute(
        "SELECT v.id, v.verdict, v.reason FROM verdicts v JOIN claims c ON c.id = v.claim_id"
        " WHERE c.question_id = ? AND c.content_sha256 = ? ORDER BY v.id DESC LIMIT 1",
        (question_id, content_sha256),
    ).fetchone()
    return Carried(row["id"], row["verdict"], row["reason"]) if row is not None else None


def citation_ids(conn: sqlite3.Connection, claim_id: str) -> builtins.list[str]:
    return [
        r[0]
        for r in conn.execute("SELECT citation_id FROM claim_citations WHERE claim_id = ? ORDER BY rowid", (claim_id,))
    ]


def for_round(conn: sqlite3.Connection, round_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute("SELECT * FROM claims WHERE round_id = ? ORDER BY ordinal", (round_id,)).fetchall()
