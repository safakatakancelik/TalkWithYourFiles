import sqlite3
from dataclasses import dataclass

from twyf import clock


@dataclass(frozen=True)
class VerdictRow:
    claim_id: str
    verdict: str
    reason: str
    carried_from: int | None = None
    supports: tuple[tuple[str, str], ...] = ()  # (citation_id, 'full' | 'partial' | 'none')


def insert(
    conn: sqlite3.Connection, *, verification_id: str, workspace_id: str, question_id: str, round_id: str,
    turn_id: str | None, passed: bool, verdicts: list[VerdictRow],
) -> None:  # fmt: skip
    conn.execute(
        "INSERT INTO verifications (id, workspace_id, question_id, round_id, turn_id, passed, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (verification_id, workspace_id, question_id, round_id, turn_id, int(passed), clock.now()),
    )
    for v in verdicts:
        cursor = conn.execute(
            "INSERT INTO verdicts (verification_id, claim_id, verdict, reason, carried_from) VALUES (?, ?, ?, ?, ?)",
            (verification_id, v.claim_id, v.verdict, v.reason, v.carried_from),
        )
        conn.executemany(
            "INSERT INTO citation_verdicts (verdict_id, citation_id, supports) VALUES (?, ?, ?)",
            [(cursor.lastrowid, cid, s) for cid, s in v.supports],
        )
