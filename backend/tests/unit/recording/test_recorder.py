import asyncio
import sqlite3

import pytest

from tests.conftest import EventsHelper
from twyf.contract.events import StatusEvent
from twyf.db.connection import transaction
from twyf.db.repos import events as events_repo
from twyf.recording.broker import BROKER, EventBroker
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

NOW = "2026-11-15T00:00:00.000Z"


def _workspace(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO workspaces VALUES ('ws_1', 'u_local', ?, NULL)", (NOW,))


def test_record_writes_all_fields(conn: sqlite3.Connection, events: EventsHelper) -> None:
    _workspace(conn)
    ctx = RequestContext(actor_id="u_local", source="ui", user_id="u_local", request_id="r1", client="browser")
    with transaction(conn):
        event_id = record(
            conn, ctx, "workspace.renamed", workspace_id="ws_1", entity_type="workspace", entity_id="ws_1",
            payload={"old": "A", "new": "B"},
        )  # fmt: skip
    row = conn.execute("SELECT * FROM app_events WHERE id = ?", (event_id,)).fetchone()
    assert (row["actor_id"], row["source"], row["user_id"], row["workspace_id"]) == ("u_local", "ui", "u_local", "ws_1")
    assert (row["request_id"], row["client"], row["entity_id"]) == ("r1", "browser", "ws_1")
    [stored] = events("workspace.renamed")
    assert stored.payload == {"old": "A", "new": "B"}
    assert stored.id == event_id


def test_record_in_same_transaction(conn: sqlite3.Connection, ctx: RequestContext, events: EventsHelper) -> None:
    def failing_service() -> None:
        with transaction(conn):
            conn.execute("INSERT INTO workspaces VALUES ('ws_2', 'u_local', ?, NULL)", (NOW,))
            record(conn, ctx, "workspace.created", workspace_id="ws_2")
            raise RuntimeError("after recording")

    with pytest.raises(RuntimeError):
        failing_service()
    assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0
    assert events() == []


def test_cause_chain(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    with transaction(conn):
        first = record(conn, ctx, "server.started")
        second = record(conn, ctx.caused_by(first), "config.changed")
    row = conn.execute("SELECT cause_event_id FROM app_events WHERE id = ?", (second,)).fetchone()
    assert row[0] == first


def test_secret_keys_rejected(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    with pytest.raises(ValueError, match="api_key"):
        record(conn, ctx, "server.started", payload={"api_key": "x"})
    with pytest.raises(ValueError, match="Authorization"):
        record(conn, ctx, "server.started", payload={"headers": [{"Authorization": "x"}]})


async def test_broker_publishes_after_commit(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    _workspace(conn)
    subscription = BROKER.subscribe("q_1")
    with transaction(conn):
        event_id = record(conn, ctx, "question.status", question_id="q_1", wire=StatusEvent(text="one"))
        await asyncio.sleep(0)
        assert BROKER._current("q_1")[0]._queue.empty()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(RuntimeError), transaction(conn):
        record(conn, ctx, "question.status", question_id="q_1", wire=StatusEvent(text="rolled back"))
        raise RuntimeError
    BROKER.close("q_1")
    received = [item async for item in subscription]
    assert received == [(event_id, StatusEvent(text="one"))]
    assert events_repo.wire_events(conn, "q_1") == [(event_id, StatusEvent(text="one"))]


async def test_broker_from_another_thread() -> None:
    broker = EventBroker()
    subscription = broker.subscribe("q_9")
    await asyncio.to_thread(broker.publish, "q_9", 3, StatusEvent(text="x"))
    await asyncio.to_thread(broker.close, "q_9")
    assert [item async for item in subscription] == [(3, StatusEvent(text="x"))]


def test_list_filters(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    _workspace(conn)
    with transaction(conn):
        a = record(conn, ctx, "workspace.created", workspace_id="ws_1")
        b = record(conn, ctx, "question.status", workspace_id="ws_1", question_id="q_1")
        c = record(conn, ctx, "server.started")
    assert [e.id for e in events_repo.list(conn, workspace_id="ws_1")] == [a, b]
    assert [e.id for e in events_repo.list(conn, question_id="q_1")] == [b]
    assert [e.id for e in events_repo.list(conn, event_type="server.started")] == [c]
    assert [e.id for e in events_repo.list(conn, after=a, limit=1)] == [b]
