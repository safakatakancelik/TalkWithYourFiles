import asyncio
import json
import sqlite3

import pytest

from tests.conftest import EventsHelper
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.turns import VolunteerInput, VolunteerOutput
from twyf.db.repos import agents as agents_repo
from twyf.recording.context import RequestContext
from twyf.runtime.base import RuntimeError_, TurnRequest, TurnResult
from twyf.runtime.fake import FakeRuntime, ScriptStep
from twyf.runtime.runner import TurnFailed, TurnRunner
from twyf.services import state

INPUT = VolunteerInput(question="When does the lease end?", broadcast_text="Who reads leases?", files=[])
GOOD = {"volunteer": True, "reason": "I read leases.", "fileIds": []}


def _translator(conn: sqlite3.Connection, ws: Workspace) -> str:
    return agents_repo.list(conn, ws.id, "translator")[0].id


def _turns(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_turns ORDER BY created_at, rowid").fetchall()


async def test_runner_records_turn(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    def answer(request: TurnRequest) -> dict[str, object]:
        return GOOD

    class WithUsage(FakeRuntime):
        async def run_turn(self, request: TurnRequest) -> TurnResult:
            result = await super().run_turn(request)
            return TurnResult.model_validate(
                {"output": result.output, "usage": {"model": "m-1", "inputTokens": 10, "outputTokens": 3}}
            )

    fake = WithUsage(answer)
    agent = _translator(conn, ws)
    output, turn_id = await TurnRunner(fake, settings, state.connect).run(
        ctx, agent_id=agent, turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
    )
    assert output.volunteer is True
    [row] = _turns(conn)
    assert (row["id"], row["state"], row["attempt"], row["runtime"]) == (turn_id, "done", 1, "fake")
    agent_row = agents_repo.get(conn, ws.id, agent)
    assert agent_row is not None and row["agent_version_id"] == agent_row.agent_version_id
    assert row["definition_version_id"] and json.loads(row["input"])["question"] == INPUT.question
    assert json.loads(row["output"]) == GOOD
    assert (row["model"], row["input_tokens"], row["output_tokens"]) == ("m-1", 10, 3)
    [request] = fake.requests
    assert request.input["broadcastText"] == "Who reads leases?" and "Your name is Translator." in request.system_prompt
    assert request.output_schema["properties"]["volunteer"]["type"] == "boolean"
    queued, completed = events("turn.queued"), events("turn.completed")
    assert len(queued) == 1 and len(completed) == 1
    assert completed[0].actor_id == agent and completed[0].source == "internal"
    assert completed[0].payload["model"] == "m-1" and completed[0].payload["input_tokens"] == 10
    assert "duration_ms" in completed[0].payload
    stored = conn.execute(
        "SELECT agent_definition_version_id FROM app_events WHERE id = ?", (completed[0].id,)
    ).fetchone()
    assert stored[0] == row["definition_version_id"]


async def test_runner_retries_invalid_output(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    fake = FakeRuntime([ScriptStep({"turn_type": "volunteer"}, {"volunteer": "maybe"}), ScriptStep({}, GOOD)])
    _, turn_id = await TurnRunner(fake, settings, state.connect).run(
        ctx, agent_id=_translator(conn, ws), turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
    )
    first, second = _turns(conn)
    assert (first["state"], second["state"], second["attempt"], second["retry_of"]) == (
        "failed",
        "done",
        2,
        first["id"],
    )
    assert second["id"] == turn_id
    assert "previousError" not in fake.requests[0].input
    assert "schema" in fake.requests[1].input["previousError"]
    assert len(events("turn.failed")) == 1


async def test_runner_validate_rules_retry(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    fake = FakeRuntime([ScriptStep({}, {**GOOD, "fileIds": ["f_unknown"]}), ScriptStep({}, GOOD)])

    def rule(out: VolunteerOutput) -> list[str]:
        return [f"unknown file {f}" for f in out.file_ids]

    await TurnRunner(fake, settings, state.connect).run(
        ctx,
        agent_id=_translator(conn, ws),
        turn_type="volunteer",
        input=INPUT,
        output_model=VolunteerOutput,
        validate=rule,
    )
    assert fake.requests[1].input["previousError"] == "unknown file f_unknown"


async def test_runner_gives_up(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    fake = FakeRuntime([ScriptStep({}, {"volunteer": "no"}, times=10)])
    with pytest.raises(TurnFailed) as raised:
        await TurnRunner(fake, settings, state.connect).run(
            ctx, agent_id=_translator(conn, ws), turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
        )
    assert raised.value.turn_type == "volunteer"
    assert len(_turns(conn)) == settings.max_turn_retries + 1
    assert {r["state"] for r in _turns(conn)} == {"failed"}


async def test_runner_runtime_error_retries(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    fake = FakeRuntime([ScriptStep({}, RuntimeError_("unavailable")), ScriptStep({}, GOOD)])
    await TurnRunner(fake, settings, state.connect).run(
        ctx, agent_id=_translator(conn, ws), turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
    )
    assert [r["state"] for r in _turns(conn)] == ["failed", "done"]


class Silent:
    name = "silent"
    capabilities = frozenset[str]()

    async def run_turn(self, request: TurnRequest) -> TurnResult:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def cancel(self, turn_id: str) -> None:
        return None


async def test_runner_timeout(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    quick = settings.model_copy(update={"turn_timeout_s": 1, "max_turn_retries": 0})
    with pytest.raises(TurnFailed):
        await TurnRunner(Silent(), quick, state.connect).run(
            ctx, agent_id=_translator(conn, ws), turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
        )
    [row] = _turns(conn)
    assert row["state"] == "timed_out"
    assert len(events("turn.timed_out")) == 1


async def test_runner_cancelled(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings, events: EventsHelper
) -> None:
    task = asyncio.create_task(
        TurnRunner(Silent(), settings, state.connect).run(
            ctx, agent_id=_translator(conn, ws), turn_type="volunteer", input=INPUT, output_model=VolunteerOutput
        )
    )
    while not _turns(conn):
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _turns(conn)[0]["state"] == "cancelled"
    assert len(events("turn.cancelled")) == 1
