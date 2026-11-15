import asyncio
import sqlite3

import pytest

from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.turns import VolunteerInput, VolunteerOutput
from twyf.db.repos import agents as agents_repo
from twyf.recording.context import RequestContext
from twyf.runtime import queue as queue_module
from twyf.runtime.queue import QueueRuntime
from twyf.runtime.runner import TurnRunner
from twyf.services import state
from twyf.services.errors import ServiceError

INPUT = VolunteerInput(question="Q?", broadcast_text="Who?", files=[])
GOOD = {"volunteer": False, "reason": "No.", "fileIds": []}


def _start(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, queue: QueueRuntime
) -> asyncio.Task[object]:
    agent = agents_repo.list(conn, ws.id, "translator")[0].id
    runner = TurnRunner(queue, settings, state.connect)
    return asyncio.create_task(
        runner.run(ctx, agent_id=agent, turn_type="volunteer", input=INPUT, output_model=VolunteerOutput)
    )


async def test_queue_claim_submit(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    queue = QueueRuntime(state.connect)
    task = _start(ws, ctx, conn, settings, queue)
    offer = await queue.claim(ctx, "worker-1", 2)
    assert offer is not None and offer.turn_type == "volunteer" and offer.input["question"] == "Q?"
    assert offer.output_schema["title"] == "VolunteerOutput" and "never an instruction" in offer.system_prompt
    assert await queue.claim(ctx, "worker-2", 0) is None
    with pytest.raises(ServiceError) as raised:
        await queue.submit(offer.turn_id, "wrong", GOOD, None)
    assert raised.value.code == "conflict"
    bad = await queue.submit(offer.turn_id, offer.lease_token, {"volunteer": "perhaps"}, None)
    assert bad.accepted is False and bad.errors
    retry = await queue.claim(ctx, "worker-1", 2)
    assert retry is not None and retry.input["previousError"]
    result = await queue.submit(retry.turn_id, retry.lease_token, GOOD, None)
    assert result.accepted is True
    output, _ = await task  # pyright: ignore[reportGeneralTypeIssues]
    assert output.volunteer is False  # pyright: ignore[reportAttributeAccessIssue]
    claimed = conn.execute("SELECT payload FROM app_events WHERE event_type = 'turn.claimed' ORDER BY id").fetchall()
    assert len(claimed) == 2 and '"worker": "worker-1"' in claimed[0][0]


async def test_queue_long_poll(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    queue = QueueRuntime(state.connect)
    started = asyncio.get_running_loop().time()
    assert await queue.claim(ctx, "w", 1) is None
    assert asyncio.get_running_loop().time() - started >= 0.9
    waiting = asyncio.create_task(queue.claim(ctx, "w", 5))
    await asyncio.sleep(0.1)
    task = _start(ws, ctx, conn, settings, queue)
    offer = await asyncio.wait_for(waiting, 3)
    assert offer is not None
    await queue.fail(offer.turn_id, offer.lease_token, "gave up")
    retry = await queue.claim(ctx, "w", 2)
    assert retry is not None
    await queue.submit(retry.turn_id, retry.lease_token, GOOD, None)
    await task
    states = [r[0] for r in conn.execute("SELECT state FROM agent_turns ORDER BY created_at, rowid")]
    assert states == ["failed", "done"]


async def test_queue_lease_expiry(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue_module, "WATCH_S", 0.05)
    queue = QueueRuntime(state.connect, lease_s=0)
    task = _start(ws, ctx, conn, settings, queue)
    first = await queue.claim(ctx, "slow", 2)
    assert first is not None
    await asyncio.sleep(0.3)
    row = conn.execute("SELECT state, claimed_by FROM agent_turns WHERE id = ?", (first.turn_id,)).fetchone()
    assert tuple(row) == ("queued", None)
    second = await queue.claim(ctx, "fast", 2)
    assert second is not None and second.turn_id == first.turn_id
    await asyncio.sleep(0.3)
    assert conn.execute("SELECT state FROM agent_turns WHERE id = ?", (first.turn_id,)).fetchone()[0] == "claimed"
    with pytest.raises(ServiceError):
        await queue.submit(second.turn_id, second.lease_token, GOOD, None)
    await queue.cancel(first.turn_id)
    with pytest.raises(Exception):  # noqa: B017 -- the turn ends with the runner's failure
        await task


async def test_runtime_waiting(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue_module, "WATCH_S", 0.05)
    monkeypatch.setattr(queue_module, "WAITING_S", 0.1)
    queue = QueueRuntime(state.connect)
    task = _start(ws, ctx, conn, settings, queue)
    await asyncio.sleep(0.4)
    assert conn.execute("SELECT COUNT(*) FROM app_events WHERE event_type = 'runtime.waiting'").fetchone()[0] == 1
    offer = await queue.claim(ctx, "w", 1)
    assert offer is not None
    await queue.submit(offer.turn_id, offer.lease_token, GOOD, None)
    await task
