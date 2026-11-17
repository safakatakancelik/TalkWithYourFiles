import asyncio
import sqlite3

from tests.integration.helpers import ENDS, LEASE, Env, Gate, happy, parse_sse
from tests.unit.orchestration.harness import (
    derived,
    q,
    quoted,
    review,
    segments,
    step,
    verdict,
    work,
)
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.contract.operations import AskInput, CreateSessionInput
from twyf.db.connection import transaction
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.recording.context import RequestContext
from twyf.runtime.fake import FakeRuntime, ScriptStep
from twyf.services import questions, sessions, state


async def test_ask_stream_format(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    response, events = await env.ask("When does the lease end?", happy(t1, f))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        assert [line.split(": ", 1)[0] for line in lines] == ["id", "event", "data"]
    assert events[0][1] == "started" and events[-1][1] == "answer"
    assert [e[0] for e in events] == sorted(e[0] for e in events)
    assert all(data["type"] == kind for _, kind, data in events)


async def test_ask_happy_path(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    _, events = await env.ask("When does the lease end?", happy(t1, f))
    kinds = [k for _, k, _ in events]
    assert kinds[0] == "started" and kinds[-1] == "answer"
    assert sum(k in ("answer", "error", "cancelled") for k in kinds) == 1
    assert kinds.index("verdict") > kinds.index("verify")
    assert kinds.index("leave") > max(i for i, k in enumerate(kinds) if k == "verdict")
    joined = {d["agentId"] for _, k, d in events if k == "join"}
    left = {a for _, k, d in events if k == "leave" for a in d["agentIds"]}
    assert joined == left
    answer = events[-1][2]
    assert answer["text"] == "The lease ends on 30 June 2029 [1]."
    assert [c["n"] for c in answer["citations"]] == [1] and answer["citations"][0]["fileName"] == "lease.txt"
    assert (
        ENDS in answer["citations"][0]["quote"] and answer["citations"][0]["quote"] in answer["citations"][0]["passage"]
    )


async def test_ask_no_files(env: Env) -> None:
    _, events = await env.ask(
        "Anything?", [step("write_answer", {"segments": [{"text": "There are no files in this workspace yet."}]})]
    )
    assert [k for _, k, _ in events] == ["started", "answer"]
    assert events[-1][2]["text"] == "There are no files in this workspace yet." and events[-1][2]["citations"] == []
    assert [r.turn_type for r in env.fake.requests] == ["write_answer"]


async def test_ask_nothing_found(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    script = happy(t1, f)[:6] + [
        step("draft_claims", {"claims": []}),
        step("write_answer", {"segments": [{"text": "The files do not say."}]}),
    ]
    _, events = await env.ask("What is the supplier's phone number?", script)
    assert events[-1][2] == {"type": "answer", "text": "The files do not say.", "citations": []}
    assert "verify" not in [r.turn_type for r in env.fake.requests]


async def test_ask_partial_after_round_limit(env: Env) -> None:
    env.settings.max_verify_rounds = 3  # the script runs three rounds; the default is lower
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    claims = {
        "claims": [
            quoted("k1", "The lease ends on 30 June 2029.", "30 June"),
            quoted("k2", "Rent rises by 10% each year.", "Rent rises"),
        ]
    }

    def round_again(i: int) -> list[ScriptStep]:
        return [
            step("review", review("continue", "Again.", [(t1, "rent", [f])])),
            step(
                "work", work([("Rent rises by 8%.", [q("Rent rises", "Rent rises by 8% each year")])]), "Translator 1"
            ),
            step("review", review("settle", "Settled.")),
            step("draft_claims", claims),
            step("verify", {"verdicts": [verdict("10%", "unsupported", ["Rent rises"], f"Says 8%, round {i}.")]}),
        ]

    script = [
        *happy(t1, f)[:4],
        step(
            "work",
            work([("Ends 2029, rent 8%.", [q("30 June", ENDS), q("Rent rises", "Rent rises by 8% each year")])]),
            "Translator 1",
        ),
        step("review", review("settle", "Settled.")),
        step("draft_claims", claims),
        step(
            "verify",
            {
                "verdicts": [
                    verdict("lease ends", "supported", ["30 June"]),
                    verdict("10%", "unsupported", ["Rent rises"], "Says 8%, round 1."),
                ]
            },
        ),
        *round_again(2),
        *round_again(3),
        step("write_answer", segments(("The lease ends on 30 June 2029.", ["lease ends"]))),
    ]
    # Rounds 2 and 3 redraft the same claims, so their verdicts are carried and their verify steps go unused.
    _, events = await env.ask("When does the lease end, and how fast does rent rise?", script)
    kinds = [k for _, k, _ in events]
    assert kinds.count("verify") == 3 and kinds.count("rehuddle") == 2
    answer = events[-1][2]
    assert answer["text"] == "The lease ends on 30 June 2029 [1]."
    assert answer["unverified"] == [{"text": "Rent rises by 10% each year.", "reason": "Says 8%, round 1."}]
    question_id = events[0][2]["questionId"]
    assert (
        env.db().execute("SELECT state FROM questions WHERE id = ?", (question_id,)).fetchone()[0] == "answered_partial"
    )


async def test_ask_mechanical_fail(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("prices.txt", "The price is 29.00 per kg.\n\nCost of goods is 13.05 per kg.")
    base = [
        quoted("k1", "The price is 29.00 per kg.", "29.00"),
        quoted("k2", "Cost of goods is 13.05 per kg.", "13.05"),
    ]
    script = [
        *happy(t1, f)[:4],
        step(
            "work",
            work(
                [("Price, cost.", [q("29.00", "price is 29.00 per kg"), q("13.05", "Cost of goods is 13.05 per kg")])]
            ),
            "Translator 1",
        ),
        step("review", review("settle", "Settled.")),
        step(
            "draft_claims",
            {"claims": [*base, derived("k3", "The margin is 60%.", ["k1", "k2"], "1 - 13.05 / 29.00", 0.6)]},
        ),
        step(
            "verify",
            {
                "verdicts": [
                    verdict("price is", "supported", ["29.00"]),
                    verdict("Cost of goods", "supported", ["13.05"]),
                ]
            },
        ),
        step("review", review("settle", "Settled.")),
        step("draft_claims", {"claims": base}),
        step("write_answer", segments(("The price is 29.00 per kg.", ["price is"]))),
    ]
    _, events = await env.ask("What is the margin?", script)
    first = next(d for _, k, d in events if k == "verdict")
    assert first["passed"] is False and first["verdicts"][2]["verdict"] == "mechanical_fail"
    assert all(
        "60%" not in c["text"] for c in next(r for r in env.fake.requests if r.turn_type == "verify").input["claims"]
    )


async def test_ask_busy_session(gated: tuple[Gate, Env]) -> None:
    gate, env = gated
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    sid = await env.session()
    first = asyncio.create_task(env.ask("When does the lease end?", happy(t1, f), session=sid))
    await gate.waiting.wait()
    response = await env.client.post(
        f"/workspaces/{await env.ws()}/sessions/{sid}/questions", json={"question": "Again?"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "conflict"
    gate.release.set()
    _, events = await first
    assert events[-1][1] == "answer"


async def test_cancel(gated: tuple[Gate, Env]) -> None:
    gate, env = gated
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    asked = asyncio.create_task(env.ask("When does the lease end?", happy(t1, f)))
    await gate.waiting.wait()
    db = env.db()
    question_id = db.execute("SELECT id FROM questions").fetchone()[0]
    response = await env.client.post(f"/workspaces/{await env.ws()}/questions/{question_id}/cancel")
    assert response.status_code == 204
    _, events = await asyncio.wait_for(asked, 5)
    assert events[-1][1] == "cancelled" and "answer" not in [k for _, k, _ in events]
    assert db.execute("SELECT state FROM questions WHERE id = ?", (question_id,)).fetchone()[0] == "cancelled"
    open_turns = db.execute(
        "SELECT COUNT(*) FROM agent_turns WHERE question_id = ? AND state IN ('queued','claimed')", (question_id,)
    ).fetchone()[0]
    assert open_turns == 0
    assert (
        db.execute(
            "SELECT COUNT(*) FROM agent_turns WHERE question_id = ? AND state = 'cancelled'", (question_id,)
        ).fetchone()[0]
        >= 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM messages WHERE question_id = ? AND role = 'assistant'", (question_id,)
        ).fetchone()[0]
        == 0
    )
    cancelled = db.execute("SELECT actor_id, source FROM app_events WHERE event_type = 'question.cancelled'").fetchone()
    assert tuple(cancelled) == ("u_local", "api")


async def test_disconnect_does_not_cancel(gated: tuple[Gate, Env], ws: Workspace, ctx: RequestContext) -> None:
    gate, env = gated
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    env.fake.script = happy(t1, f)
    ws_id = await env.ws()
    session = sessions.create(ctx, CreateSessionInput(ws=ws_id, title="S"))
    stream = questions.ask(ctx, AskInput(ws=ws_id, session_id=session.id, question="When does the lease end?"))
    first_id, first = await anext(stream)
    assert first.type == "started"
    await stream.aclose()
    gate.release.set()
    question_id = first.question_id  # pyright: ignore[reportAttributeAccessIssue]
    await state.tasks().wait(question_id)
    db = env.db()
    assert db.execute("SELECT state FROM questions WHERE id = ?", (question_id,)).fetchone()[0] == "answered"
    assert first_id > 0


async def test_replay(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    _, events = await env.ask("When does the lease end?", happy(t1, f))
    question_id = events[0][2]["questionId"]
    ws = await env.ws()
    middle = events[4][0]
    replay = parse_sse(
        (await env.client.get(f"/workspaces/{ws}/questions/{question_id}/events", params={"after": middle})).text
    )
    assert replay == [e for e in events if e[0] > middle]
    polled = (await env.client.get(f"/workspaces/{ws}/questions/{question_id}/events", params={"after": middle},
                                   headers={"Accept": "application/json"})).json()  # fmt: skip
    assert polled["done"] is True and polled["lastId"] == events[-1][0]
    assert polled["events"] == [d for i, _, d in events if i > middle]
    missing = await env.client.get(f"/workspaces/{ws}/questions/q_nope/events")
    assert missing.status_code == 404


async def test_crash_recovery(settings: Settings, ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    session = sessions.create(ctx, CreateSessionInput(ws=ws.id, title="S"))
    question_id = questions.start(ctx, AskInput(ws=ws.id, session_id=session.id, question="Left running?"))
    agent = conn.execute(
        "SELECT id, definition_id, agent_version_id FROM v_agents WHERE workspace_id = ? AND agent_kind = 'orchestrator'",
        (ws.id,),
    ).fetchone()
    dv = conn.execute(
        "SELECT id FROM agent_definition_versions WHERE definition_id = ? AND valid_to IS NULL",
        (agent["definition_id"],),
    ).fetchone()[0]
    with transaction(conn):
        conn.execute("UPDATE questions SET state = 'working' WHERE id = ?", (question_id,))
        conn.execute(
            "INSERT INTO agent_turns (id, workspace_id, question_id, agent_id, agent_version_id, definition_version_id,"
            " turn_type, state, runtime, system_prompt, input, created_at) VALUES ('t_left', ?, ?, ?, ?, ?, 'plan',"
            " 'queued', 'fake', 's', '{}', '2026-11-16T00:00:00.000Z')",
            (ws.id, question_id, agent["id"], agent["agent_version_id"], dv),
        )
    app = build_app(settings, runtime=FakeRuntime([]), jobs=InlineJobs())
    async with app.router.lifespan_context(app):
        pass
    row = conn.execute("SELECT state, finished_at FROM questions WHERE id = ?", (question_id,)).fetchone()
    assert row["state"] == "interrupted" and row["finished_at"] is not None
    assert conn.execute("SELECT state FROM agent_turns WHERE id = 't_left'").fetchone()[0] == "cancelled"
    event = conn.execute("SELECT actor_id, source FROM app_events WHERE event_type = 'question.interrupted'").fetchone()
    assert tuple(event) == ("system", "internal")
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM messages WHERE question_id = ? AND role = 'user'", (question_id,)
        ).fetchone()[0]
        == 1
    )


async def test_sessions_and_messages(env: Env) -> None:
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    older = await env.session()
    sid = await env.session()
    await env.ask("When does the lease end?", happy(t1, f), session=older)
    ws = await env.ws()
    listed = [s["id"] for s in (await env.client.get(f"/workspaces/{ws}/sessions")).json()]
    assert listed[0] == older and sid in listed
    user, answer = (await env.client.get(f"/workspaces/{ws}/sessions/{older}/messages")).json()
    assert (user["role"], user["text"]) == ("user", "When does the lease end?")
    assert answer["role"] == "assistant" and answer["text"] == "The lease ends on 30 June 2029 [1]."
    assert answer["citations"][0]["n"] == 1 and answer["citations"][0]["fileVersion"] == 1


async def test_delete_conflicts(gated: tuple[Gate, Env]) -> None:
    gate, env = gated
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    sid = await env.session()
    asked = asyncio.create_task(env.ask("When does the lease end?", happy(t1, f), session=sid))
    await gate.waiting.wait()
    ws = await env.ws()
    for path in (f"/workspaces/{ws}/agents/{t1}", f"/workspaces/{ws}/sessions/{sid}"):
        response = await env.client.delete(path)
        assert response.status_code == 409, path
    gate.release.set()
    await asked
    assert (await env.client.delete(f"/workspaces/{ws}/agents/{t1}")).status_code == 204
