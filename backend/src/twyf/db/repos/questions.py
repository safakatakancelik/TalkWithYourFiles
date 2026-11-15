import builtins
import sqlite3

from twyf import clock


def insert(
    conn: sqlite3.Connection, *, question_id: str, workspace_id: str, session_id: str, max_rounds: int,
    config_version_id: int, runtime: str,
) -> None:  # fmt: skip
    conn.execute(
        "INSERT INTO questions (id, workspace_id, session_id, state, max_rounds, config_version_id, runtime, started_at)"
        " VALUES (?, ?, ?, 'received', ?, ?, ?, ?)",
        (question_id, workspace_id, session_id, max_rounds, config_version_id, runtime, clock.now()),
    )


def get(conn: sqlite3.Connection, workspace_id: str, question_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM questions WHERE workspace_id = ? AND id = ?", (workspace_id, question_id)
    ).fetchone()


def by_id(conn: sqlite3.Connection, question_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()


def set_state(conn: sqlite3.Connection, question_id: str, state: str) -> None:
    conn.execute("UPDATE questions SET state = ? WHERE id = ?", (state, question_id))


def set_rounds(conn: sqlite3.Connection, question_id: str, rounds: int) -> None:
    conn.execute("UPDATE questions SET rounds_used = ? WHERE id = ?", (rounds, question_id))


def finish(
    conn: sqlite3.Connection, question_id: str, *, state: str, error_code: str | None = None,
    error_message: str | None = None,
) -> tuple[int, int]:  # fmt: skip
    """Final state and the token totals of the question's turns."""
    totals = conn.execute(
        "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM agent_turns WHERE question_id = ?",
        (question_id,),
    ).fetchone()
    conn.execute(
        "UPDATE questions SET state = ?, error_code = ?, error_message = ?, input_tokens = ?, output_tokens = ?,"
        " finished_at = ? WHERE id = ?",
        (state, error_code, error_message, totals[0], totals[1], clock.now(), question_id),
    )
    return totals[0], totals[1]


def running_in_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM questions WHERE session_id = ? AND finished_at IS NULL LIMIT 1", (session_id,)
    ).fetchone()


def open_questions(conn: sqlite3.Connection, workspace_id: str | None = None) -> builtins.list[sqlite3.Row]:
    sql = "SELECT * FROM questions WHERE finished_at IS NULL"
    args: builtins.list[str] = []
    if workspace_id is not None:
        sql += " AND workspace_id = ?"
        args.append(workspace_id)
    return conn.execute(sql + " ORDER BY started_at", args).fetchall()


def open_turns(conn: sqlite3.Connection, question_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM agent_turns WHERE question_id = ? AND state IN ('queued', 'claimed')", (question_id,)
    ).fetchall()
