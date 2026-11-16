"""Appends to app_events inside the caller's transaction. Every action that changes state is recorded here."""

import json
import sqlite3
from typing import Any, cast

from twyf import clock
from twyf.contract.events import AgentEvent
from twyf.contract.models import dump
from twyf.db.connection import after_commit
from twyf.recording import broker
from twyf.recording.context import RequestContext

SECRET_KEYS = frozenset({"api_key", "token", "authorization", "password"})


def _check_secrets(value: Any) -> None:
    if isinstance(value, dict):
        for key, inner in cast(dict[object, Any], value).items():
            if isinstance(key, str) and key.lower() in SECRET_KEYS:
                raise ValueError(f"payload key {key!r} may hold a secret and is not recorded")
            _check_secrets(inner)
    elif isinstance(value, list):
        for inner in cast(list[Any], value):
            _check_secrets(inner)


def _definition_in_force(conn: sqlite3.Connection, actor_id: str) -> int | None:
    """An agent's action records the definition version it acts under (02-data-model.md section 3)."""
    row = conn.execute(
        "SELECT d.id FROM agent_versions v JOIN agent_definition_versions d ON d.definition_id = v.definition_id"
        " AND d.valid_to IS NULL WHERE v.agent_id = ? AND v.valid_to IS NULL",
        (actor_id,),
    ).fetchone()
    return row[0] if row is not None else None


def record(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    event_type: str,
    *,
    workspace_id: str | None = None,
    session_id: str | None = None,
    question_id: str | None = None,
    round_id: str | None = None,
    turn_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    wire: AgentEvent | None = None,
    definition_version_id: int | None = None,
    config_version_id: int | None = None,
) -> int:
    """Inserts one event and returns its id. A wire event is published to the question's streams on commit."""
    payload = payload or {}
    _check_secrets(payload)
    if definition_version_id is None:
        definition_version_id = _definition_in_force(conn, ctx.actor_id)
    if turn_id is not None and question_id is None:
        turn = conn.execute("SELECT question_id, round_id FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()
        if turn is not None:
            question_id, round_id = turn["question_id"], round_id or turn["round_id"]
    cursor = conn.execute(
        "INSERT INTO app_events (occurred_at, event_type, actor_id, source, client, user_id, workspace_id,"
        " session_id, question_id, round_id, turn_id, request_id, cause_event_id, entity_type, entity_id,"
        " agent_definition_version_id, config_version_id, payload, wire_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            clock.now(),
            event_type,
            ctx.actor_id,
            ctx.source,
            ctx.client,
            ctx.user_id,
            workspace_id,
            session_id,
            question_id,
            round_id,
            turn_id,
            ctx.request_id,
            ctx.cause_event_id,
            entity_type,
            entity_id,
            definition_version_id,
            config_version_id,
            json.dumps(payload, sort_keys=True),
            json.dumps(dump(wire)) if wire is not None else None,
        ),
    )
    event_id = cursor.lastrowid
    assert event_id is not None
    if wire is not None and question_id is not None:
        event, qid = wire, question_id
        after_commit(conn, lambda: broker.BROKER.publish(qid, event_id, event))
    return event_id
