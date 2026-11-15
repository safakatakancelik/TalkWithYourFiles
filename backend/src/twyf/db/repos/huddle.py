import builtins
import sqlite3

from twyf import clock


def start_round(
    conn: sqlite3.Connection, *, round_id: str, workspace_id: str, question_id: str, round_no: int, reason: str
) -> None:
    now = clock.now()
    conn.execute("UPDATE huddle_rounds SET ended_at = ? WHERE question_id = ? AND ended_at IS NULL", (now, question_id))
    conn.execute(
        "INSERT INTO huddle_rounds (id, workspace_id, question_id, round_no, reason, started_at) VALUES (?, ?, ?, ?, ?, ?)",
        (round_id, workspace_id, question_id, round_no, reason, now),
    )


def end_rounds(conn: sqlite3.Connection, question_id: str) -> None:
    conn.execute(
        "UPDATE huddle_rounds SET ended_at = ? WHERE question_id = ? AND ended_at IS NULL", (clock.now(), question_id)
    )


def join(conn: sqlite3.Connection, *, workspace_id: str, question_id: str, agent_id: str, how: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO huddle_members (workspace_id, question_id, agent_id, how, joined_at) VALUES (?, ?, ?, ?, ?)",
        (workspace_id, question_id, agent_id, how, clock.now()),
    )


def leave(conn: sqlite3.Connection, question_id: str, agent_ids: builtins.list[str], reason: str) -> None:
    conn.executemany(
        "UPDATE huddle_members SET left_at = ?, left_reason = ? WHERE question_id = ? AND agent_id = ? AND left_at IS NULL",
        [(clock.now(), reason, question_id, a) for a in agent_ids],
    )


def running_members(conn: sqlite3.Connection, agent_id: str) -> builtins.list[sqlite3.Row]:
    """Huddles this agent is in, in questions that are still running."""
    return conn.execute(
        "SELECT m.* FROM huddle_members m JOIN questions q ON q.id = m.question_id"
        " WHERE m.agent_id = ? AND m.left_at IS NULL AND q.finished_at IS NULL",
        (agent_id,),
    ).fetchall()


def assign(
    conn: sqlite3.Connection, *, workspace_id: str, question_id: str | None, round_id: str | None, agent_id: str,
    file_id: str, file_version_id: str, purpose: str,
) -> None:  # fmt: skip
    conn.execute(
        "INSERT INTO assignments (workspace_id, question_id, round_id, agent_id, file_id, file_version_id, purpose,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (workspace_id, question_id, round_id, agent_id, file_id, file_version_id, purpose, clock.now()),
    )


def add_statement(
    conn: sqlite3.Connection, *, workspace_id: str, question_id: str | None, round_id: str | None, turn_id: str,
    agent_id: str, text: str, citation_ids: builtins.list[str],
) -> int:  # fmt: skip
    cursor = conn.execute(
        "INSERT INTO statements (workspace_id, question_id, round_id, turn_id, agent_id, text, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (workspace_id, question_id, round_id, turn_id, agent_id, text, clock.now()),
    )
    assert cursor.lastrowid is not None
    conn.executemany(
        "INSERT INTO statement_citations (statement_id, citation_id, n) VALUES (?, ?, ?)",
        [(cursor.lastrowid, cid, n) for n, cid in enumerate(citation_ids, start=1)],
    )
    return cursor.lastrowid
