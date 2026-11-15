"""The default runtime: turns wait in the database until a harness claims and answers them (04-agents.md 6.3)."""

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from twyf import clock
from twyf.contract.events import StatusEvent
from twyf.contract.models import SubmitResult
from twyf.contract.turns import TurnOffer, Usage
from twyf.db.connection import transaction
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.runtime.base import RuntimeError_, TurnRequest, TurnResult
from twyf.services.errors import ServiceError

log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]
WAITING_S = 10.0
WATCH_S = 1.0
SYSTEM = RequestContext(actor_id="system", source="internal", user_id="u_local", request_id="queue")


def _later(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Pending:
    request: TurnRequest
    future: asyncio.Future[TurnResult]
    queued_at: float = field(default_factory=time.monotonic)
    requeued: bool = False
    warned: bool = False


class QueueRuntime:
    name = "queue"
    capabilities = frozenset({"vision"})

    def __init__(self, conn_factory: ConnFactory, lease_s: int = 300) -> None:
        self.conn_factory = conn_factory
        self.lease_s = lease_s
        self.pending: dict[str, Pending] = {}
        self._queued = asyncio.Event()
        self._watcher: asyncio.Task[None] | None = None

    def _db[T](self, fn: Callable[[sqlite3.Connection], T]) -> T:
        conn = self.conn_factory()
        try:
            with transaction(conn):
                return fn(conn)
        finally:
            conn.close()

    # --- the runtime side ------------------------------------------------------------------------------------

    async def run_turn(self, request: TurnRequest) -> TurnResult:
        """Leaves the turn queued and waits until a harness submits it, fails it, or it is cancelled."""
        future: asyncio.Future[TurnResult] = asyncio.get_running_loop().create_future()
        self.pending[request.turn_id] = Pending(request, future)
        self._queued.set()
        if self._watcher is None or self._watcher.done():
            self._watcher = asyncio.get_running_loop().create_task(self._watch())
        try:
            return await future
        finally:
            self.pending.pop(request.turn_id, None)

    async def cancel(self, turn_id: str) -> None:
        pending = self.pending.get(turn_id)
        if pending is not None and not pending.future.done():
            pending.future.set_exception(RuntimeError_("cancelled", "the question ended"))

    async def _watch(self) -> None:
        """Every second: put a turn whose lease expired back to queued (once), and say when nobody is working."""
        while self.pending:
            await asyncio.sleep(WATCH_S)
            await asyncio.to_thread(self._db, self._check)

    def _check(self, conn: sqlite3.Connection) -> None:
        now = clock.now()
        for turn_id, pending in list(self.pending.items()):
            row = conn.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()
            if row is None:
                continue
            if row["state"] == "claimed" and row["lease_expires_at"] < now and not pending.requeued:
                pending.requeued = True
                conn.execute(
                    "UPDATE agent_turns SET state = 'queued', claimed_by = NULL, lease_token = NULL, lease_expires_at = NULL"
                    " WHERE id = ?",
                    (turn_id,),
                )
                self._queued.set()
            elif row["state"] == "queued" and not pending.warned and time.monotonic() - pending.queued_at >= WAITING_S:
                pending.warned = True
                wire = StatusEvent(
                    text="No agent runtime is connected. The question waits until a worker claims its turns."
                )
                record(conn, SYSTEM.as_actor("system"), "runtime.waiting", workspace_id=row["workspace_id"],
                       question_id=row["question_id"], turn_id=turn_id, entity_type="turn", entity_id=turn_id,
                       payload={"turn_type": row["turn_type"]}, wire=wire if row["question_id"] else None)  # fmt: skip

    # --- the harness side: claim, submit, fail ---------------------------------------------------------------

    def _try_claim(self, ctx: RequestContext, worker: str) -> TurnOffer | None:
        ids = list(self.pending)
        if not ids:
            return None
        token, expires = new_id("lease"), _later(self.lease_s)

        def claim(conn: sqlite3.Connection) -> sqlite3.Row | None:
            marks = ", ".join("?" for _ in ids)
            row = conn.execute(
                "UPDATE agent_turns SET state = 'claimed', claimed_by = ?, lease_token = ?, lease_expires_at = ?"
                f" WHERE id = (SELECT id FROM agent_turns WHERE state = 'queued' AND id IN ({marks})"
                " ORDER BY created_at, rowid LIMIT 1) AND state = 'queued' RETURNING *",
                [worker, token, expires, *ids],
            ).fetchone()
            if row is not None:
                record(conn, ctx.as_actor(row["agent_id"], ctx.source), "turn.claimed", workspace_id=row["workspace_id"],
                       question_id=row["question_id"], round_id=row["round_id"], turn_id=row["id"], entity_type="turn",
                       entity_id=row["id"], payload={"worker": worker}, definition_version_id=row["definition_version_id"])  # fmt: skip
            return row

        row = self._db(claim)
        if row is None or row["id"] not in self.pending:
            return None
        request = self.pending[row["id"]].request
        return TurnOffer(
            turn_id=request.turn_id, lease_token=token, turn_type=request.turn_type, agent_name=request.agent_name,
            agent_kind=request.agent_kind, system_prompt=request.system_prompt, instructions=request.instructions,
            input=request.input, output_schema=request.output_schema, expires_at=expires,
        )  # fmt: skip

    async def claim(self, ctx: RequestContext, worker: str, wait_s: int) -> TurnOffer | None:
        """The oldest queued turn, or nothing after waiting up to `wait_s` seconds."""
        deadline = time.monotonic() + max(0, wait_s)
        while True:
            self._queued.clear()
            offer = await asyncio.to_thread(self._try_claim, ctx, worker)
            left = deadline - time.monotonic()
            if offer is not None or left <= 0:
                return offer
            try:
                await asyncio.wait_for(self._queued.wait(), timeout=min(left, WATCH_S))
            except TimeoutError:
                pass

    def _lease(self, turn_id: str, lease_token: str) -> Pending:
        pending = self.pending.get(turn_id)
        row = self._db(lambda c: c.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone())
        if row is None:
            raise ServiceError("not_found", "No such turn", {"turn_id": turn_id})
        stale = (
            pending is None or pending.future.done() or row["state"] != "claimed" or row["lease_token"] != lease_token
            or row["lease_expires_at"] < clock.now()
        )  # fmt: skip
        if stale or pending is None:
            raise ServiceError("conflict", "The lease is wrong or has expired", {"turn_id": turn_id})
        return pending

    async def submit(self, turn_id: str, lease_token: str, output: dict[str, Any], usage: Usage | None) -> SubmitResult:
        """Hands the output to the runner and waits for its validation. A rejected output comes back as a retry."""
        pending = await asyncio.to_thread(self._lease, turn_id, lease_token)
        pending.future.set_result(TurnResult(output=output, usage=usage or Usage()))
        for _ in range(3000):
            row = await asyncio.to_thread(
                self._db,
                lambda c: c.execute("SELECT state, error FROM agent_turns WHERE id = ?", (turn_id,)).fetchone(),
            )
            if row["state"] != "claimed":
                if row["state"] == "done":
                    return SubmitResult(accepted=True)
                return SubmitResult(accepted=False, errors=[e for e in (row["error"] or "").split("; ") if e])
            await asyncio.sleep(0.01)
        return SubmitResult(accepted=False, errors=["the output was not processed in time"])

    async def fail(self, turn_id: str, lease_token: str, reason: str) -> None:
        pending = await asyncio.to_thread(self._lease, turn_id, lease_token)
        pending.future.set_exception(RuntimeError_("unavailable", reason))
