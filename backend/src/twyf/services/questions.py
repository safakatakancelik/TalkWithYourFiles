import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from twyf.agents.definitions import sync, sync_config
from twyf.contract.events import AgentEvent, QuestionEvents, StartedEvent
from twyf.contract.operations import AskInput, CancelQuestionInput, GetQuestionEventsInput
from twyf.db.connection import transaction
from twyf.db.repos import events as events_repo
from twyf.db.repos import questions as repo
from twyf.db.repos import turns as turns_repo
from twyf.ids import new_id
from twyf.recording.broker import BROKER, EventBroker
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.sessions import add_message, live
from twyf.services.workspaces import require


def start(ctx: RequestContext, input: AskInput) -> str:
    """Validates, rejects a busy session, stores the user message and the question, records question.asked."""
    text = require_text(input.question, "question")
    settings = state.settings()
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        live(conn, input.ws, input.session_id)
        if repo.running_in_session(conn, input.session_id) is not None:
            raise ServiceError(
                "conflict", "This session already has a running question", {"session_id": input.session_id}
            )
        system = ctx.as_actor("system", "internal")
        sync(conn, system, settings)
        config_id = sync_config(conn, system, settings)
        question_id = new_id("q")
        repo.insert(
            conn, question_id=question_id, workspace_id=input.ws, session_id=input.session_id,
            max_rounds=settings.max_verify_rounds, config_version_id=config_id, runtime=settings.runtime,
        )  # fmt: skip
        add_message(conn, ctx, workspace_id=input.ws, session_id=input.session_id, role="user", text=text,
                    question_id=question_id)  # fmt: skip
        record(
            conn, ctx, "question.asked", workspace_id=input.ws, session_id=input.session_id, question_id=question_id,
            entity_type="question", entity_id=question_id, payload={"question": text},
            wire=StartedEvent(question_id=question_id), config_version_id=config_id,
        )  # fmt: skip
        return question_id


log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]
FINAL_EVENTS = frozenset({"answer", "error", "cancelled"})


class Tasks:
    """The engine tasks of running questions. Only `cancel_question` cancels one; a closed stream does not."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._background: set[asyncio.Task[None]] = set()

    def start_background(self, coro: Coroutine[Any, Any, None]) -> None:
        """Work outside a question (first reads, image descriptions), kept until done."""
        task = asyncio.get_running_loop().create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background_done)

    def _background_done(self, task: asyncio.Task[None]) -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("background work failed", exc_info=task.exception())

    async def wait_background(self) -> None:
        while self._background:
            await asyncio.gather(*self._background, return_exceptions=True)

    def start(self, question_id: str, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro, name=f"question {question_id}")
        self._tasks[question_id] = task
        task.add_done_callback(lambda t: self._done(question_id, t))

    def _done(self, question_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(question_id, None)
        if not task.cancelled() and task.exception() is not None:
            log.error("question %s failed", question_id, exc_info=task.exception())

    def cancel(self, question_id: str) -> bool:
        task = self._tasks.get(question_id)
        if task is None:
            return False
        task.cancel()
        return True

    def running(self) -> list[str]:
        return list(self._tasks)

    async def wait(self, question_id: str) -> None:
        task = self._tasks.get(question_id)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)


def _finished(conn_factory: ConnFactory, question_id: str) -> bool:
    conn = conn_factory()
    try:
        row = repo.by_id(conn, question_id)
        return row is None or row["finished_at"] is not None
    finally:
        conn.close()


def _stored(conn_factory: ConnFactory, question_id: str, after: int) -> list[tuple[int, AgentEvent]]:
    conn = conn_factory()
    try:
        return events_repo.wire_events(conn, question_id, after)
    finally:
        conn.close()


async def follow(
    broker: EventBroker, conn_factory: ConnFactory, question_id: str, after: int
) -> AsyncIterator[tuple[int, AgentEvent]]:
    """The stored events after `after`, then live ones until the final event. No id is sent twice."""
    subscription = broker.subscribe(question_id)
    last = after
    try:
        for event_id, event in await asyncio.to_thread(_stored, conn_factory, question_id, after):
            last = event_id
            yield event_id, event
            if event.type in FINAL_EVENTS:
                return
        if await asyncio.to_thread(_finished, conn_factory, question_id):
            return
        async for event_id, event in subscription:
            if event_id <= last:
                continue
            last = event_id
            yield event_id, event
            if event.type in FINAL_EVENTS:
                return
    finally:
        subscription.close()


def _question(conn: sqlite3.Connection, ws_id: str, question_id: str) -> sqlite3.Row:
    row = repo.get(conn, ws_id, question_id)
    if row is None:
        raise ServiceError("not_found", "No such question", {"question_id": question_id})
    return row


async def ask(ctx: RequestContext, input: AskInput) -> AsyncIterator[tuple[int, AgentEvent]]:
    """Starts the question and streams its events. The engine runs on whether or not anyone listens."""
    question_id = await asyncio.to_thread(start, ctx, input)
    state.tasks().start(question_id, state.engine().run(ctx, question_id))
    async for item in follow(BROKER, state.connect, question_id, 0):
        yield item


async def events(ctx: RequestContext, input: GetQuestionEventsInput) -> AsyncIterator[tuple[int, AgentEvent]]:
    with state.db() as conn:
        require(conn, input.ws)
        _question(conn, input.ws, input.question_id)
    async for item in follow(BROKER, state.connect, input.question_id, input.after or 0):
        yield item


def events_now(ctx: RequestContext, input: GetQuestionEventsInput) -> QuestionEvents:
    """The polling form: every stored event after `after`, the last id, and whether the question is over."""
    with state.db() as conn:
        require(conn, input.ws)
        row = _question(conn, input.ws, input.question_id)
        stored = events_repo.wire_events(conn, input.question_id, input.after or 0)
        return QuestionEvents(
            events=[e for _, e in stored], last_id=stored[-1][0] if stored else input.after or 0,
            done=row["finished_at"] is not None,
        )  # fmt: skip


def cancel(ctx: RequestContext, input: CancelQuestionInput) -> None:
    """The only thing that cancels a question. A finished question is left as it is."""
    with state.db() as conn:
        require(conn, input.ws)
        row = _question(conn, input.ws, input.question_id)
    if row["finished_at"] is not None:
        return
    state.cancel_question(input.question_id, ctx)


def recover(conn: sqlite3.Connection, ctx: RequestContext) -> int:
    """At start: every question left in a non-final state is interrupted and its open turns cancelled."""
    count = 0
    with transaction(conn):
        for row in repo.open_questions(conn):
            for turn in repo.open_turns(conn, row["id"]):
                turns_repo.finish(conn, turn["id"], state="cancelled", error="server restarted")
                record(conn, ctx.as_actor(turn["agent_id"]), "turn.cancelled", workspace_id=row["workspace_id"],
                       question_id=row["id"], turn_id=turn["id"], entity_type="turn", entity_id=turn["id"],
                       definition_version_id=turn["definition_version_id"])  # fmt: skip
            repo.finish(conn, row["id"], state="interrupted")
            record(conn, ctx, "question.interrupted", workspace_id=row["workspace_id"], session_id=row["session_id"],
                   question_id=row["id"], entity_type="question", entity_id=row["id"], payload={"from": row["state"]})  # fmt: skip
            count += 1
    return count
