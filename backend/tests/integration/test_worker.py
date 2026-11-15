import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from tests.integration.helpers import LEASE, Env, happy, parse_sse
from twyf.config import Settings
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.runtime.base import TurnRequest
from twyf.runtime.fake import FakeRuntime, resolve
from twyf.runtime.queue import QueueRuntime
from twyf.services import state


@pytest.fixture
async def queued(settings: Settings) -> AsyncIterator[Env]:
    app = build_app(
        settings.model_copy(update={"runtime": "queue"}), runtime=QueueRuntime(state.connect), jobs=InlineJobs()
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c,
    ):
        yield Env(c, FakeRuntime([]), settings)


async def test_question_completed_by_a_worker(queued: Env) -> None:
    env = queued
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    script = FakeRuntime(happy(t1, f))
    sid = await env.session()
    asked = asyncio.create_task(
        env.client.post(f"/workspaces/{await env.ws()}/sessions/{sid}/questions", json={"question": "When?"})
    )
    done = 0
    while not asked.done():
        offer = (await env.client.post("/runtime/turns/claim", json={"worker": "harness-1", "waitS": 1})).json()
        if offer is None:
            continue
        answer: dict[str, Any] = script._answer(_request(offer))  # pyright: ignore[reportPrivateUsage, reportAssignmentType]
        output = resolve(answer, offer["input"], offer["turnType"])
        result = (await env.client.post(f"/runtime/turns/{offer['turnId']}/submit",
                                        json={"leaseToken": offer["leaseToken"], "output": output})).json()  # fmt: skip
        assert result == {"accepted": True}, result
        done += 1
    events = parse_sse((await asyncio.wait_for(asked, 5)).text)
    assert events[-1][1] == "answer" and done == 8  # Translator 2 is not asked
    rows = env.db().execute("SELECT payload FROM app_events WHERE event_type = 'turn.claimed'").fetchall()
    assert len(rows) == 8 and all('"worker": "harness-1"' in r[0] for r in rows)
    bad = await env.client.post("/runtime/turns/t_nope/submit", json={"leaseToken": "x", "output": {}})
    assert bad.status_code == 404


def _request(offer: dict[str, Any]) -> TurnRequest:
    return TurnRequest(
        turn_id=offer["turnId"], turn_type=offer["turnType"], agent_name=offer["agentName"], agent_kind=offer["agentKind"],
        system_prompt=offer["systemPrompt"], instructions=offer["instructions"], input=offer["input"],
        output_schema=offer["outputSchema"], timeout_s=60,
    )  # fmt: skip
