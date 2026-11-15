from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from tests.integration.helpers import ENDS, LEASE, Env
from tests.unit.orchestration.harness import assign, q, quoted, review, segments, step, verdict, volunteer, work
from tests.unit.orchestration.harness import plan as plan_out
from twyf.citations.check import check
from twyf.config import Settings
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.retrieval.keyword import search
from twyf.runtime.fake import FakeRuntime, ScriptStep, resolve
from twyf.services import state


@pytest.fixture
async def reading(settings: Settings) -> AsyncIterator[Env]:
    """An app with the first read switched on."""
    fake = FakeRuntime([])
    app = build_app(settings.model_copy(update={"first_read": True}), runtime=fake, jobs=InlineJobs())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c,
    ):
        yield Env(c, fake, settings)


async def test_ask_translator(env: Env) -> None:
    t1 = (await env.translators())[0]
    await env.upload("lease.txt", LEASE)
    env.fake.script = [step("direct_reply", {
        "statements": [{"text": "It ends on 30 June 2029.", "quotes": [q("30 June", ENDS)]}],
        "notes": [], "searches": [],
    })]  # fmt: skip
    ws = await env.ws()
    reply = (
        await env.client.post(f"/workspaces/{ws}/agents/{t1}/ask", json={"question": "When does the lease end?"})
    ).json()
    assert reply["text"] == "It ends on 30 June 2029."
    [citation] = reply["citations"]
    assert citation["n"] == 1 and citation["quote"] == ENDS
    db = env.db()
    assert check(db, citation["id"]).ok
    events = [r[0] for r in db.execute("SELECT event_type FROM app_events ORDER BY id")]
    assert "translator.asked" in events and "translator.replied" in events
    assert db.execute("SELECT purpose FROM assignments WHERE agent_id = ?", (t1,)).fetchone()[0] == "direct"
    assert [r.turn_type for r in env.fake.requests] == ["direct_reply"]


def first_read_output(needle: str, quote: str, file_id: str, entity: str) -> dict[str, Any]:
    return {
        "summary": {
            "fileId": file_id,
            "kind": "summary",
            "text": "A lease that runs to 2029.",
            "quotes": [q(needle, quote)],
        },
        "entities": [{"label": entity, "type": "place", "passageId": {"$passage": needle}}],
    }


async def test_first_read(reading: Env) -> None:
    def answer(request: Any) -> dict[str, Any]:
        file_id = request.input["passages"][0]["fileId"]
        return resolve(first_read_output("30 June", ENDS, file_id, "Quay Street"), request.input, request.turn_type)

    reading.fake.script = answer
    f = await reading.upload("lease.txt", LEASE)
    await state.tasks().wait_background()
    turns = [r for r in reading.fake.requests if r.turn_type == "first_read"]
    assert len(turns) == 1
    ws = await reading.ws()
    [note] = (await reading.client.get(f"/workspaces/{ws}/notes")).json()
    assert note["kind"] == "summary" and note["fileId"] == f and note["citations"][0]["quote"] == ENDS
    db = reading.db()
    assert db.execute("SELECT purpose FROM assignments WHERE file_id = ?", (f,)).fetchone()[0] == "first_read"
    graph = (await reading.client.get(f"/workspaces/{ws}/context-map")).json()
    assert "Quay Street" in [n["label"] for n in graph["nodes"]]


async def test_no_first_read_when_off(env: Env) -> None:
    await env.upload("other.txt", LEASE)
    await state.tasks().wait_background()
    assert not [r for r in env.fake.requests if r.turn_type == "first_read"]


async def test_long_file_stays_bounded(reading: Env) -> None:
    paragraphs = [f"Paragraph {i}. " + "Plain filler words for the record. " * 28 for i in range(3000)]
    paragraphs[2500] = "Paragraph 2500. The zephyrine clause sets the renewal fee at four percent. " + "Filler. " * 100

    def answer(request: Any) -> dict[str, Any]:
        file_id = request.input["passages"][0]["fileId"]
        return resolve(
            first_read_output("Paragraph 0.", "Paragraph 0. Plain filler words", file_id, "Record"),
            request.input,
            "first_read",
        )

    reading.fake.script = answer
    f = await reading.upload("long.txt", "\n\n".join(paragraphs))
    await state.tasks().wait_background()
    [first] = [r for r in reading.fake.requests if r.turn_type == "first_read"]
    assert len(first.input["passages"]) == reading.settings.first_read_chunks
    assert first.input["chunksShown"] == reading.settings.first_read_chunks and first.input["chunksTotal"] == 3000
    t1 = (await reading.translators())[0]
    fee = "zephyrine clause sets the renewal fee at four percent"
    reading.fake.script = [
        step("plan", plan_out([t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("volunteer", volunteer(False), "Translator 2"),
        step("assign", assign((t1, [f], "renewal fee"))),
        step("work", work([("The fee is four percent.", [q("zephyrine", fee)])]), "Translator 1"),
        step("review", review("settle", "Settled.")),
        step("draft_claims", {"claims": [quoted("k1", "The renewal fee is four percent.", "zephyrine")]}),
        step("verify", {"verdicts": [verdict("renewal fee", "supported", ["zephyrine"])]}),
        step("write_answer", segments(("The renewal fee is four percent.", ["renewal fee"]))),
    ]
    _, events = await reading.ask("What does the zephyrine clause set?", reading.fake.script)
    assert events[-1][1] == "answer"
    works = [r for r in reading.fake.requests if r.turn_type == "work"]
    limit = reading.settings.passages_per_turn * (1 + reading.settings.searches_per_turn)
    assert all(len(w.input["passages"]) <= limit for w in works)
    assert any("zephyrine" in p["text"] for p in works[0].input["passages"])
    assert len([r for r in reading.fake.requests if r.turn_type == "first_read"]) == 1


async def test_image_gets_a_searchable_description(env: Env) -> None:
    env.fake.script = [
        ScriptStep({"turn_type": "describe_image"}, {"description": "A bar chart of monthly coffee sales by channel."})
    ]
    f = await env.upload("chart.png", b"\x89PNG\r\n\x1a\n not really an image")
    await state.tasks().wait_background()
    [request] = env.fake.requests
    assert request.attachments[0].media_type == "image/png" and request.input["fileName"] == "chart.png"
    db = env.db()
    kind, text = db.execute("SELECT kind, text FROM extractions WHERE status = 'ok'").fetchone()
    assert kind == "description" and "coffee sales" in text
    ws = await env.ws()
    [item] = (await env.client.get(f"/workspaces/{ws}/files")).json()
    assert item["id"] == f and item["status"] == "ready"
    assert search(db, workspace_id=ws, query="coffee sales", file_ids=None, k=5)
