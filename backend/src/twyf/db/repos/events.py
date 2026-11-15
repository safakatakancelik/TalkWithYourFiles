import builtins
import json
import sqlite3

from twyf.contract.events import AgentEvent, parse_event
from twyf.contract.models import EventRecord

_FIELDS = (
    "workspace_id",
    "session_id",
    "question_id",
    "round_id",
    "turn_id",
    "cause_event_id",
    "entity_type",
    "entity_id",
)


def to_record(row: sqlite3.Row) -> EventRecord:
    optional = {name: row[name] for name in _FIELDS if row[name] is not None}
    return EventRecord(
        id=row["id"],
        occurred_at=row["occurred_at"],
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        source=row["source"],
        payload=json.loads(row["payload"]),
        **optional,
    )


def list(
    conn: sqlite3.Connection,
    *,
    workspace_id: str | None = None,
    question_id: str | None = None,
    event_type: str | None = None,
    after: int | None = None,
    limit: int = 200,
) -> builtins.list[EventRecord]:
    where: builtins.list[str] = []
    args: builtins.list[object] = []
    for column, value in (("workspace_id", workspace_id), ("question_id", question_id), ("event_type", event_type)):
        if value is not None:
            where.append(f"{column} = ?")
            args.append(value)
    if after is not None:
        where.append("id > ?")
        args.append(after)
    sql = "SELECT * FROM app_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id LIMIT ?"
    args.append(limit)
    return [to_record(row) for row in conn.execute(sql, args)]


def wire_events(conn: sqlite3.Connection, question_id: str, after: int = 0) -> builtins.list[tuple[int, AgentEvent]]:
    rows = conn.execute(
        "SELECT id, wire_json FROM app_events WHERE question_id = ? AND wire_json IS NOT NULL AND id > ? ORDER BY id",
        (question_id, after),
    )
    return [(row["id"], parse_event(json.loads(row["wire_json"]))) for row in rows]
