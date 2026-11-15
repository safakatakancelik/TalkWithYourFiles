import json
import sqlite3
from typing import Any

from twyf import clock


def insert(
    conn: sqlite3.Connection,
    *,
    turn_id: str,
    workspace_id: str,
    question_id: str | None,
    round_id: str | None,
    agent_id: str,
    agent_version_id: int,
    definition_version_id: int,
    turn_type: str,
    attempt: int,
    retry_of: str | None,
    runtime: str,
    system_prompt: str,
    input: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO agent_turns (id, workspace_id, question_id, round_id, agent_id, agent_version_id,"
        " definition_version_id, turn_type, attempt, retry_of, state, runtime, system_prompt, input, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
        (turn_id, workspace_id, question_id, round_id, agent_id, agent_version_id, definition_version_id, turn_type,
         attempt, retry_of, runtime, system_prompt, json.dumps(input), clock.now()),
    )  # fmt: skip


def get(conn: sqlite3.Connection, workspace_id: str, turn_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM agent_turns WHERE workspace_id = ? AND id = ?", (workspace_id, turn_id)
    ).fetchone()


def by_id(conn: sqlite3.Connection, turn_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()


def mark_started(conn: sqlite3.Connection, turn_id: str) -> None:
    conn.execute("UPDATE agent_turns SET started_at = ? WHERE id = ? AND started_at IS NULL", (clock.now(), turn_id))


def finish(
    conn: sqlite3.Connection,
    turn_id: str,
    *,
    state: str,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int | None = None,
) -> None:
    """Sets a final state. Turn state is type 1 on the row; every change is also in app_events."""
    conn.execute(
        "UPDATE agent_turns SET state = ?, output = ?, error = ?, model = ?, input_tokens = ?, output_tokens = ?,"
        " duration_ms = ?, finished_at = ? WHERE id = ?",
        (state, json.dumps(output) if output is not None else None, error, model, input_tokens, output_tokens,
         duration_ms, clock.now(), turn_id),
    )  # fmt: skip
