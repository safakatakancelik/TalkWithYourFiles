import json
import re
import sqlite3
from typing import Any

import httpx
import pytest

from tests.conftest import DEMO_FIXTURES
from tests.integration.helpers import parse_sse
from twyf.citations.check import check
from twyf.citations.locate import create_citation
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.recording.context import RequestContext
from twyf.runtime.fake import FakeRuntime
from twyf.services import demo as demo_service
from twyf.services import state
from twyf.services.errors import ServiceError

DEMO_QUESTION = (
    "Our coffee supplier is raising prices in January. Can we keep our current prices and still hit our margin target?"
)
ANSWER = (
    "Not without changing something. From 1 January 2027, Andes Green Coffee raises its price by 8% [1]. "
    "At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9% [1][2]. "
    "That is below the board's 55% target [3].\n\n"
    "The board also decided to hold retail prices until March 2027 [3]. "
    "The pricing policy requires a review only when cost of goods moves more than 5% [4]. "
    "This change is about 4.7%, so the policy does not force one [1][2][4]. "
    "To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7% [1][2][3]. "
    "The price hold and the margin target cannot both be kept [1][2][3]. This needs a board decision."
)
STORY_QUOTES = {
    "f-contract": ["From 1 January 2027 the Price shall increase by eight percent (8%)"],
    "f-sales": ["avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60"],
    "f-board": ["hold retail prices at current levels until the March 2027 meeting"],
    "f-pricing": ["A price review is required whenever cost of goods moves by more than 5%"],
}


def test_demo_fixtures_parse(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    from tests.conftest import upload

    for file_id, name in demo_service.FILES.items():
        item = upload(ctx, ws.id, name, (DEMO_FIXTURES / name).read_bytes(), file_id=f"{file_id}-x")
        assert item.status == "ready", name
    agent = conn.execute(
        "SELECT id FROM v_agents WHERE workspace_id = ? AND agent_kind = 'orchestrator'", (ws.id,)
    ).fetchone()[0]
    quotes = {
        f: [q for n in demo_service.NOTES if n[1] == f for q in n[4]] + STORY_QUOTES.get(f, [])
        for f in demo_service.FILES
    }
    quotes["f-lease"].append("shall expire on 30 June 2029")
    for file_id, wanted in quotes.items():
        for quote in wanted:
            passage = demo_service.passage_with(conn, f"{file_id}-x", quote)
            row = create_citation(
                conn, ctx, workspace_id=ws.id, passage_id=passage, quote=quote, agent_id=agent, turn_id=None
            )
            assert row.quote == quote and quote in row.passage
    board = demo_service.passage_with(conn, "f-board-x", STORY_QUOTES["f-board"][0])
    k3 = create_citation(
        conn, ctx, workspace_id=ws.id, passage_id=board, quote=STORY_QUOTES["f-board"][0], agent_id=agent, turn_id=None
    )
    assert "The gross margin target for the financial year remains 55%" in k3.passage
    sales = create_citation(conn, ctx, workspace_id=ws.id, passage_id=demo_service.passage_with(conn, "f-sales-x", STORY_QUOTES["f-sales"][0]),
                            quote=STORY_QUOTES["f-sales"][0], agent_id=agent, turn_id=None)  # fmt: skip
    assert sales.location == "Row 4" and sales.passage.startswith("channel=Total Q3 2026, total_kg=5150")


def test_demo_seed(demo: str, conn: sqlite3.Connection, ctx: RequestContext, settings: Settings) -> None:
    assert demo == "demo"
    assert (
        conn.execute("SELECT name FROM v_workspaces WHERE id = 'demo'").fetchone()[0] == "Harbor Coffee Roasters (demo)"
    )
    assert {r[0] for r in conn.execute("SELECT id FROM v_files WHERE workspace_id = 'demo'")} == set(demo_service.FILES)
    translators = conn.execute(
        "SELECT id, name, specialty FROM v_agents WHERE workspace_id = 'demo' AND agent_kind = 'translator'"
    ).fetchall()
    assert {tuple(r) for r in translators} == set(demo_service.TRANSLATORS)
    notes = conn.execute("SELECT id, author_id, kind, weight FROM v_notes WHERE workspace_id = 'demo'").fetchall()
    assert {r["id"] for r in notes} == {n[0] for n in demo_service.NOTES}
    assert all(r["kind"] == "summary" and r["weight"] == "normal" for r in notes)
    for note_id, *_ in demo_service.NOTES:
        cited = [r[0] for r in conn.execute("SELECT citation_id FROM note_citations WHERE note_id = ?", (note_id,))]
        assert cited and all(check(conn, c).ok for c in cited)
    assert {r[0] for r in conn.execute("SELECT id FROM entities WHERE workspace_id = 'demo'")} == {
        e[0] for e in demo_service.ENTITIES
    }
    assert conn.execute("SELECT COUNT(*) FROM entity_mentions WHERE workspace_id = 'demo'").fetchone()[0] == 9
    messages = conn.execute(
        "SELECT role, text FROM messages WHERE session_id = 's-lease' ORDER BY created_at, rowid"
    ).fetchall()
    assert [tuple(m) for m in messages] == [
        ("user", "When does the office lease end?"),
        ("assistant", demo_service.LEASE_ANSWER),
    ]
    [seeded] = conn.execute("SELECT actor_id, source FROM app_events WHERE event_type = 'demo.seeded'").fetchall()
    assert tuple(seeded) == ("system", "cli")
    with pytest.raises(ServiceError) as raised:
        demo_service.seed(ctx, settings, DEMO_FIXTURES)
    assert raised.value.code == "conflict"


async def _run_demo(
    client: httpx.AsyncClient, fake: FakeRuntime
) -> tuple[list[tuple[int, str, dict[str, Any]]], dict[str, Any]]:
    fake.script = FakeRuntime.from_file(DEMO_FIXTURES / "script.json").script
    before = {
        "files": (await client.get("/workspaces/demo/files")).json(),
        "agents": (await client.get("/workspaces/demo/agents")).json(),
        "map": (await client.get("/workspaces/demo/context-map")).json(),
        "notes": (await client.get("/workspaces/demo/notes")).json(),
    }
    session = (await client.post("/workspaces/demo/sessions", json={"title": "test"})).json()
    response = await client.post(
        f"/workspaces/demo/sessions/{session['id']}/questions", json={"question": DEMO_QUESTION}
    )
    events = parse_sse(response.text)
    await state.tasks().wait(events[0][2]["questionId"])
    return events, before


async def test_demo_question(demo: str, client: httpx.AsyncClient, fake: FakeRuntime) -> None:
    events, before = await _run_demo(client, fake)
    data = [d for _, _, d in events]

    def of(kind: str) -> list[dict[str, Any]]:
        return [d for d in data if d["type"] == kind]

    files, agents = before["files"], before["agents"]
    # The existing checks of scenario.test.ts.
    assert sorted(of("broadcast")[0]["to"]) == sorted(a["id"] for a in agents)
    joins = of("join")
    assert len([j for j in joins if j["how"] == "volunteered"]) == 3
    assert [j["agentId"] for j in joins if j["how"] == "called"] == ["a-t2"]
    assert len(agents) - len(joins) == 1
    assigns = of("assign")
    assert sorted(a["agentId"] for a in assigns) == sorted(j["agentId"] for j in joins)
    assert all(any(f["id"] == a["fileId"] for f in files) for a in assigns)
    written = [e["note"] for e in of("note")]
    assert len(written) == 5
    for n in written:
        assert any(a["agentId"] == n["authorId"] and a["fileId"] == n["fileId"] for a in assigns)
        assert n["citations"] and all(c["fileId"] == n["fileId"] for c in n["citations"])
    notes_after = (await client.get("/workspaces/demo/notes")).json()
    assert len(notes_after) == len(before["notes"]) + 5
    assert (
        await client.post("/workspaces/demo/notes/weight", json={"noteIds": [written[0]["id"]], "weight": "off"})
    ).status_code == 204
    assert (
        next(n for n in (await client.get("/workspaces/demo/notes")).json() if n["id"] == written[0]["id"])["weight"]
        == "off"
    )
    members = {"orchestrator", *(j["agentId"] for j in joins)}
    assert all(s["agentId"] in members for s in of("say"))
    assert sorted(a for leave in of("leave") for a in leave["agentIds"]) == sorted(j["agentId"] for j in joins)
    assert data[-1]["type"] == "answer"
    answer = of("answer")[0]
    markers = {int(m) for m in re.findall(r"\[(\d+)\]", answer["text"])}
    assert markers == {c["n"] for c in answer["citations"]}
    for c in answer["citations"]:
        assert any(f["id"] == c["fileId"] for f in files) and any(a["id"] == c["agentId"] for a in agents)
        assert c["quote"] in c["passage"]
    after = (await client.get("/workspaces/demo/context-map")).json()
    assert len(after["nodes"]) > len(before["map"]["nodes"])
    # The checks of 10-demo-scenario.md section 6.
    assert data[0]["type"] == "started"
    for note in before["notes"]:
        if note["kind"] == "summary" and note["authorId"] != "user":
            assert note["citations"] and all(c["quote"] in c["passage"] for c in note["citations"])
    assert all(s.get("citations") for s in of("say") if s["agentId"] != "orchestrator")
    assert not [s for s in of("say") if s["agentId"] == "verifier"]
    verifies, verdicts = of("verify"), of("verdict")
    assert len(verifies) == 2 and len(verdicts) == 2
    assert (
        verdicts[0]["passed"] is False and len([v for v in verdicts[0]["verdicts"] if v["verdict"] != "supported"]) == 1
    )
    kinds = [d["type"] for d in data]
    for i, verify in enumerate(verifies):
        assert sorted(v["claimId"] for v in verdicts[i]["verdicts"]) == sorted(c["id"] for c in verify["claims"])
    [rehuddle] = of("rehuddle")
    failed = [v["claimId"] for v in verdicts[0]["verdicts"] if v["verdict"] != "supported"]
    assert rehuddle["round"] == 2 and rehuddle["claimIds"] == failed
    assert kinds.index("rehuddle") == kinds.index("verdict") + 1
    between = data[kinds.index("rehuddle") : len(kinds) - 1 - kinds[::-1].index("verify")]
    assert any(d["type"] == "say" and d.get("citations") for d in between)
    assert verdicts[1]["passed"] is True
    assert kinds.index("leave") > len(kinds) - 1 - kinds[::-1].index("verdict")
    assert not answer.get("unverified")
    # And the backend's own: the exact text, every scripted step used, and only the new claims verified again.
    assert answer["text"] == ANSWER
    assert fake.unused() == []
    assert len(json.loads((DEMO_FIXTURES / "script.json").read_text())) == 23  # the 17 rows of section 5, per agent
    verify_turns = [r for r in fake.requests if r.turn_type == "verify"]
    assert sorted(c["text"] for c in verify_turns[1].input["claims"]) == sorted([
        "The pricing policy requires a price review when cost of goods moves by more than 5%.",
        "Cost of goods rises by about 4.7%, which is below the 5% review trigger.",
        "The price hold and the 55% margin target cannot both be kept.",
    ])  # fmt: skip


async def test_demo_recording(
    demo: str, client: httpx.AsyncClient, fake: FakeRuntime, conn: sqlite3.Connection
) -> None:
    events, _ = await _run_demo(client, fake)
    question_id = events[0][2]["questionId"]
    rows = conn.execute("SELECT * FROM app_events WHERE question_id = ? ORDER BY id", (question_id,)).fetchall()
    first = list(dict.fromkeys(r["event_type"] for r in rows))
    story = [
        "message.created", "question.asked", "question.state_changed", "huddle.round_started", "turn.queued", "turn.completed",
        "huddle.broadcast", "huddle.member_joined", "huddle.file_assigned", "huddle.reading", "retrieval.searched",
        "citation.created", "huddle.statement", "note.created", "claims.drafted", "verification.started",
        "verification.completed", "huddle.reopened", "huddle.member_left", "context.extended", "answer.written",
        "question.completed",
    ]  # fmt: skip
    assert [t for t in first if t in story] == story
    agents = {r[0] for r in conn.execute("SELECT id FROM agents WHERE workspace_id = 'demo'")}
    agent_events = [r for r in rows if r["actor_id"] in agents]
    assert agent_events and all(r["agent_definition_version_id"] is not None for r in agent_events)
    [completed] = [r for r in rows if r["event_type"] == "question.completed"]
    payload = json.loads(completed["payload"])
    assert {"input_tokens", "output_tokens", "seconds", "rounds"} <= set(payload) and payload["rounds"] == 2
