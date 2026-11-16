"""07-test-plan.md section 7: every kind of action is recorded with the right actor, source, workspace and links."""

import asyncio
import inspect
import itertools
import json
import shutil
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import DEMO_FIXTURES, REPO_ROOT
from tests.integration import test_demo
from tests.integration.helpers import ENDS, LEASE, Env, Gate, happy
from tests.unit.orchestration.harness import q, quoted, review, segments, step, verdict, work
from twyf.config import Settings
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.recording.context import RequestContext
from twyf.runtime.base import RuntimeError_
from twyf.runtime.fake import FakeRuntime
from twyf.runtime.queue import QueueRuntime
from twyf.services import demo as demo_service
from twyf.services import state

type Case = Callable[["R"], Awaitable[None]]

# The edges of the state diagram in 04-agents.md section 5.1, plus cancel and fatal from any non-final state.
VALID_PATHS = {
    ("received", "planning"), ("received", "writing"), ("planning", "broadcasting"), ("planning", "assigning"),
    ("broadcasting", "assigning"), ("assigning", "working"), ("assigning", "drafting"), ("working", "reviewing"),
    ("reviewing", "working"), ("reviewing", "drafting"), ("drafting", "verifying"), ("drafting", "writing"),
    ("verifying", "writing"), ("verifying", "reviewing"), ("writing", "answered"), ("writing", "answered_partial"),
} | {(s, end) for s in ("received", "planning", "broadcasting", "assigning", "working", "reviewing", "drafting",
                       "verifying", "writing") for end in ("cancelled", "failed")}  # fmt: skip


class R:
    """What a case works with: the API, the scripted runtime, and the event log since the case began."""

    def __init__(self, env: Env) -> None:
        self.env, self.client, self.fake, self.settings = env, env.client, env.fake, env.settings
        self.db: sqlite3.Connection = env.db()
        self.start = self.last_id()

    def last_id(self) -> int:
        return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM app_events").fetchone()[0]

    def new(self, event_type: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM app_events WHERE id > ? AND event_type = ? ORDER BY id", (self.start, event_type)
        ).fetchall()

    def one(self, event_type: str, actor: str, source: str, ws: str | None) -> sqlite3.Row:
        [row] = self.new(event_type)
        assert (row["actor_id"], row["source"], row["workspace_id"]) == (actor, source, ws), (event_type, tuple(row))
        return row

    def agent_of(self, ws: str, kind: str) -> str:
        return self.db.execute(
            "SELECT id FROM v_agents WHERE workspace_id = ? AND agent_kind = ?", (ws, kind)
        ).fetchone()[0]

    def location(self, file_id: str) -> Path:
        return (
            self.settings.data_dir
            / self.db.execute("SELECT location FROM v_files WHERE id = ?", (file_id,)).fetchone()[0]
        )


def payload(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["payload"])


async def rich_question(r: R) -> tuple[str, str, str, str]:
    """A question with a rejected quote, a failed verification, a rehuddle and an answer. (ws, t1, file, question)"""
    env = r.env
    ws = await env.ws()
    t1 = (await env.translators())[0]
    f = await env.upload("lease.txt", LEASE)
    r.start = r.last_id()
    script = [
        *happy(t1, f)[:4],
        step("work", work([("It ends in 2031.", [q("30 June", "the lease ends in July 2031")])]), "Translator 1"),
        step(
            "work",
            work(
                [("It ends on 30 June 2029.", [q("30 June", ENDS)])],
                entities=[{"label": "Quay Street", "type": "place", "passageId": {"$passage": "30 June"}}],
            ),
            "Translator 1",
        ),
        step("review", review("settle", "We have it.")),
        step("draft_claims", {"claims": [quoted("k1", "The lease ends on 30 June 2029 and renews.", "30 June")]}),
        step(
            "verify", {"verdicts": [verdict("and renews", "partly_supported", ["30 June"], "Nothing says it renews.")]}
        ),
        step("review", review("continue", "Check renewal.", [(t1, "renewal", [f])])),
        step(
            "work", work([("No renewal is mentioned; it ends on 30 June 2029.", [q("30 June", ENDS)])]), "Translator 1"
        ),
        step("review", review("settle", "Settled.")),
        step("draft_claims", {"claims": [quoted("k1", "The lease ends on 30 June 2029.", "30 June")]}),
        step("verify", {"verdicts": [verdict("lease ends on 30 June 2029.", "supported", ["30 June"])]}),
        step("write_answer", segments(("The lease ends on 30 June 2029.", ["lease ends"]))),
    ]
    _, events = await env.ask("When does the lease end?", script)
    assert events[-1][1] == "answer"
    return ws, t1, f, events[0][2]["questionId"]


# --- the cases, one per row of the table ---------------------------------------------------------------------


async def workspace_crud(r: R) -> None:
    ws = (await r.client.post("/workspaces", json={"name": "W"})).json()["id"]
    await r.client.patch(f"/workspaces/{ws}", json={"name": "W2"})
    await r.client.delete(f"/workspaces/{ws}")
    for kind in ("workspace.created", "workspace.renamed", "workspace.deleted"):
        assert r.one(kind, "u_local", "api", ws)["entity_id"] == ws


async def upload_from_ui(r: R) -> None:
    ws = await r.env.ws()
    item = (
        await r.client.post(
            f"/workspaces/{ws}/files", files={"file": ("a.txt", b"Some text here.")}, headers={"X-TWYF-Source": "ui"}
        )
    ).json()
    uploaded = r.one("file.uploaded", "u_local", "ui", ws)
    assert uploaded["entity_id"] == item["id"]
    for kind in ("file.extraction_completed", "file.indexed"):
        row = r.one(kind, "system", "internal", ws)
        assert row["cause_event_id"] == uploaded["id"]


async def upload_duplicate(r: R) -> None:
    ws = await r.env.ws()
    await r.env.upload("a.txt", "Same bytes.")
    r.start = r.last_id()
    count = r.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    await r.env.upload("a.txt", "Same bytes.")
    r.one("file.upload_duplicate", "u_local", "api", ws)
    assert r.db.execute("SELECT COUNT(*) FROM files").fetchone()[0] == count


async def add_version(r: R) -> None:
    ws = await r.env.ws()
    f = await r.env.upload("a.txt", "One.")
    r.start = r.last_id()
    await r.client.post(f"/workspaces/{ws}/files/{f}/versions", files={"file": ("a.txt", b"Two.")})
    added = r.one("file.version_added", "u_local", "api", ws)
    assert r.db.execute("SELECT MAX(version) FROM file_versions WHERE file_id = ?", (f,)).fetchone()[0] == 2
    started = r.one("file.ingest_started", "system", "internal", ws)
    assert started["id"] > added["id"]


async def availability(r: R) -> None:
    ws = await r.env.ws()
    f = await r.env.upload("a.txt", "Original bytes.")
    path = r.location(f)
    r.start = r.last_id()
    steps: list[tuple[str, Callable[[], object]]] = [
        ("file.missing", path.unlink), ("file.restored", lambda: path.write_bytes(b"Original bytes.")),
        ("file.changed", lambda: path.write_bytes(b"Other bytes.")),
    ]  # fmt: skip
    for kind, change in steps:
        change()
        await r.client.get(f"/workspaces/{ws}/files", headers={"X-Request-Id": f"check-{kind}"})
        row = r.one(kind, "system", "internal", ws)
        assert row["entity_id"] == f and row["request_id"] == f"check-{kind}"


async def deletes(r: R) -> None:
    ws = await r.env.ws()
    f = await r.env.upload("a.txt", "Text.")
    agent = (await r.client.post(f"/workspaces/{ws}/agents", json={"name": "T", "specialty": "generic"})).json()["id"]
    keep = await r.env.upload("b.txt", "More.")
    note = (await r.client.post(f"/workspaces/{ws}/notes", json={"fileId": keep, "text": "N"})).json()["id"]
    session = await r.env.session()
    r.start = r.last_id()
    for path, kind, table, key in (
        (f"/files/{f}", "file.deleted", "files", f), (f"/agents/{agent}", "agent.deleted", "agents", agent),
        (f"/notes/{note}", "note.deleted", "notes", note), (f"/sessions/{session}", "session.deleted", "sessions", session),
    ):  # fmt: skip
        await r.client.delete(f"/workspaces/{ws}{path}")
        r.one(kind, "u_local", "api", ws)
        assert r.db.execute(f"SELECT deleted_at FROM {table} WHERE id = ?", (key,)).fetchone()[0] is not None


async def renames_and_edits(r: R) -> None:
    ws = await r.env.ws()
    t1 = (await r.env.translators())[0]
    session = await r.env.session()
    f = await r.env.upload("a.txt", "Text.")
    note = (await r.client.post(f"/workspaces/{ws}/notes", json={"fileId": f, "text": "Old"})).json()["id"]
    r.start = r.last_id()
    await r.client.patch(f"/workspaces/{ws}/agents/{t1}", json={"name": "Reader"})
    await r.client.patch(f"/workspaces/{ws}/sessions/{session}", json={"title": "New"})
    await r.client.patch(f"/workspaces/{ws}/notes/{note}", json={"text": "New text"})
    for kind, table, key_col, key, new in (
        ("agent.renamed", "agent_versions", "agent_id", t1, "Reader"),
        ("session.renamed", "session_versions", "session_id", session, "New"),
        ("note.edited", "note_versions", "note_id", note, "New text"),
    ):
        row = r.one(kind, "u_local", "api", ws)
        assert payload(row)["new"] == new and "old" in payload(row)
        assert r.db.execute(f"SELECT COUNT(*) FROM {table} WHERE {key_col} = ?", (key,)).fetchone()[0] == 2


async def create_agent_through_mcp(r: R) -> None:
    ws = await r.env.ws()
    await r.client.post(f"/workspaces/{ws}/agents", json={"name": "L", "specialty": "contracts"},
                        headers={"X-TWYF-Source": "mcp", "X-TWYF-Client": "claude-code"})  # fmt: skip
    assert r.one("agent.created", "u_local", "mcp", ws)["client"] == "claude-code"


async def workspace_creation_agents(r: R) -> None:
    ws = (await r.client.post("/workspaces", json={"name": "W"})).json()["id"]
    rows = r.new("agent.created")
    assert len(rows) == 5 and all(
        (x["actor_id"], x["source"], x["workspace_id"]) == ("system", "internal", ws) for x in rows
    )
    kinds = sorted(payload(x)["kind"] for x in rows)
    assert kinds == ["chat", "orchestrator", "translator", "translator", "verifier"]


async def add_user_note(r: R) -> None:
    ws = await r.env.ws()
    f = await r.env.upload("a.txt", "Text.")
    r.start = r.last_id()
    await r.client.post(f"/workspaces/{ws}/notes", json={"fileId": f, "text": "Mine"})
    r.one("note.created", "u_local", "api", ws)


async def weights(r: R) -> None:
    ws = await r.env.ws()
    f = await r.env.upload("a.txt", "Text.")
    ids = [
        (await r.client.post(f"/workspaces/{ws}/notes", json={"fileId": f, "text": f"N{i}"})).json()["id"]
        for i in range(3)
    ]
    r.start = r.last_id()
    await r.client.post(f"/workspaces/{ws}/notes/weight", json={"noteIds": ids, "weight": "low"})
    rows = r.new("note.weight_set")
    assert len(rows) == 3 and all(payload(x) == {"old": "normal", "new": "low"} and x["source"] == "api" for x in rows)


async def create_session(r: R) -> None:
    ws = await r.env.ws()
    await r.env.session()
    r.one("session.created", "u_local", "api", ws)


async def ask(r: R) -> None:
    ws, _, _, question = await rich_question(r)
    asked = r.one("question.asked", "u_local", "api", ws)
    assert asked["question_id"] == question and asked["config_version_id"] is not None


async def state_changes(r: R) -> None:
    _, _, _, _question = await rich_question(r)
    rows = r.new("question.state_changed")
    assert all((x["actor_id"], x["source"]) == ("system", "internal") for x in rows)
    path = [(payload(x)["from"], payload(x)["to"]) for x in rows]
    assert path[0][0] == "received" and all(a[1] == b[0] for a, b in itertools.pairwise(path))
    assert all(pair in VALID_PATHS for pair in path) and path[-1][1] == "answered"


def _cause_reaches_asked(db: sqlite3.Connection, row: sqlite3.Row) -> bool:
    cause = row["cause_event_id"]
    while cause is not None:
        found = db.execute("SELECT event_type, cause_event_id FROM app_events WHERE id = ?", (cause,)).fetchone()
        if found["event_type"] == "question.asked":
            return True
        cause = found["cause_event_id"]
    return False


async def huddle_events(r: R) -> None:
    ws, t1, _, question = await rich_question(r)
    orchestrator = r.agent_of(ws, "orchestrator")
    expected = {"huddle.broadcast": orchestrator, "huddle.member_joined": t1, "huddle.file_assigned": orchestrator,
                "huddle.reading": t1, "huddle.statement": None}  # fmt: skip
    for kind, actor in expected.items():
        rows = r.new(kind)
        assert rows, kind
        for row in rows:
            assert row["source"] == "internal" and row["question_id"] == question and row["round_id"], kind
            assert actor is None or row["actor_id"] == actor, kind
            assert _cause_reaches_asked(r.db, row), kind
    assert {x["actor_id"] for x in r.new("huddle.statement")} == {t1, orchestrator}


async def assignment_without_note(r: R) -> None:
    ws, t1, _f, question = await rich_question(r)
    assert r.new("huddle.file_assigned")[0]["actor_id"] == r.agent_of(ws, "orchestrator")
    assert (
        r.db.execute(
            "SELECT COUNT(*) FROM assignments WHERE question_id = ? AND agent_id = ?", (question, t1)
        ).fetchone()[0]
        == 1
    )
    assert r.db.execute("SELECT COUNT(*) FROM notes WHERE question_id = ?", (question,)).fetchone()[0] == 0


async def turns(r: R) -> None:
    await rich_question(r)
    for kind in ("turn.queued", "turn.completed"):
        for row in r.new(kind):
            turn = r.db.execute(
                "SELECT agent_id, definition_version_id FROM agent_turns WHERE id = ?", (row["turn_id"],)
            ).fetchone()
            assert (row["actor_id"], row["source"]) == (turn["agent_id"], "internal")
            assert row["agent_definition_version_id"] == turn["definition_version_id"]
    assert all(
        {"model", "input_tokens", "output_tokens", "duration_ms"} <= set(payload(x)) for x in r.new("turn.completed")
    )
    assert r.new("turn.failed"), "the rejected quote fails a turn"


async def search(r: R) -> None:
    _, t1, _, question = await rich_question(r)
    rows = r.new("retrieval.searched")
    assert rows and all(x["actor_id"] == t1 and x["question_id"] == question for x in rows)
    assert all(payload(x)["query"] and payload(x)["chunk_ids"] for x in rows)


async def quotes(r: R) -> None:
    _, t1, _, _ = await rich_question(r)
    for kind in ("citation.created", "citation.rejected"):
        rows = r.new(kind)
        assert rows and all((x["actor_id"], x["source"]) == (t1, "internal") for x in rows), kind


async def verification(r: R) -> None:
    ws, _, _, _ = await rich_question(r)
    verifier, orchestrator = r.agent_of(ws, "verifier"), r.agent_of(ws, "orchestrator")
    assert {x["actor_id"] for x in r.new("verification.started") + r.new("verification.completed")} == {verifier}
    assert [x["actor_id"] for x in r.new("huddle.reopened")] == [orchestrator]
    claims = r.db.execute("SELECT id, round_id FROM claims").fetchall()
    for row in r.new("verification.completed"):
        listed = {v["claim_id"] for v in payload(row)["verdicts"]}
        assert listed == {c["id"] for c in claims if c["round_id"] == row["round_id"]}


async def answer(r: R) -> None:
    ws, _, _, _ = await rich_question(r)
    chat = r.agent_of(ws, "chat")
    r.one("answer.written", chat, "internal", ws)
    assert [x["actor_id"] for x in r.new("message.created")] == ["u_local", chat]
    r.one("question.completed", "system", "internal", ws)


async def cancel(r: R) -> None:
    gate = Gate(FakeRuntime([]))
    app = build_app(r.settings, runtime=gate, jobs=InlineJobs())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as c,
    ):
        env = Env(c, gate.inner, r.settings)
        t1 = (await env.translators())[0]
        f = await env.upload("lease.txt", LEASE)
        asked = asyncio.create_task(env.ask("When?", happy(t1, f)))
        await gate.waiting.wait()
        question = r.db.execute("SELECT id FROM questions WHERE finished_at IS NULL").fetchone()[0]
        await c.post(f"/workspaces/{await env.ws()}/questions/{question}/cancel")
        await asyncio.wait_for(asked, 5)
        assert r.one("question.cancelled", "u_local", "api", await env.ws())["question_id"] == question
        assert r.new("turn.cancelled")


async def direct_chat(r: R) -> None:
    ws = await r.env.ws()
    t1 = (await r.env.translators())[0]
    await r.env.upload("lease.txt", LEASE)
    r.fake.script = [
        step(
            "direct_reply",
            {"statements": [{"text": "It ends in 2029.", "quotes": [q("30 June", ENDS)]}], "notes": [], "searches": []},
        )
    ]
    r.start = r.last_id()
    await r.client.post(f"/workspaces/{ws}/agents/{t1}/ask", json={"question": "When?"})
    r.one("translator.asked", "u_local", "api", ws)
    r.one("translator.replied", t1, "internal", ws)


async def definition_edit(r: R) -> None:
    agents_dir = r.settings.data_dir / "agents-copy" / ".agents"
    shutil.copytree(REPO_ROOT / ".agents", agents_dir)
    settings = r.settings.model_copy(update={"agents_dir": agents_dir})
    fake = FakeRuntime([])
    app = build_app(settings, runtime=fake, jobs=InlineJobs())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as c,
    ):
        env = Env(c, fake, settings)
        t1 = (await env.translators())[0]
        f = await env.upload("lease.txt", LEASE)
        _, first = await env.ask("When?", happy(t1, f))
        md = agents_dir / "agents" / "translator" / "agent.md"
        md.write_text(md.read_text() + "\nOne more line.\n")
        r.start = r.last_id()
        _, second = await env.ask("When?", happy(t1, f))
    loaded = [x for x in r.new("definition.loaded") if x["entity_id"] == "translator"]
    assert len(loaded) == 1 and (loaded[0]["actor_id"], loaded[0]["source"]) == ("system", "internal")

    def versions(question: str) -> set[int]:
        rows = r.db.execute(
            "SELECT definition_version_id FROM agent_turns WHERE question_id = ? AND agent_id = ?", (question, t1)
        )
        return {x[0] for x in rows}

    before, after = versions(first[0][2]["questionId"]), versions(second[0][2]["questionId"])
    assert after == {loaded[0]["agent_definition_version_id"]} and before.isdisjoint(after)


async def config_change(r: R) -> None:
    app = build_app(r.settings.model_copy(update={"max_verify_rounds": 5}), runtime=FakeRuntime([]), jobs=InlineJobs())
    async with app.router.lifespan_context(app):
        pass
    row = r.one("config.changed", "system", "internal", None)
    assert payload(row)["config"]["max_verify_rounds"] == 5


async def demo_seeded(r: R) -> None:
    ctx = RequestContext(actor_id="system", source="cli", user_id="u_local", request_id="seed")
    await asyncio.to_thread(demo_service.seed, ctx, r.settings, DEMO_FIXTURES)
    r.one("demo.seeded", "system", "cli", "demo")


# --- event types not named in the table, so that each is asserted somewhere -------------------------------------


async def server_started(r: R) -> None:
    app = build_app(r.settings, runtime=FakeRuntime([]), jobs=InlineJobs())
    async with app.router.lifespan_context(app):
        pass
    r.one("server.started", "system", "internal", None)
    assert r.new("skill.loaded") == [] or all(x["actor_id"] == "system" for x in r.new("skill.loaded"))


async def skill_change(r: R) -> None:
    agents_dir = r.settings.data_dir / "agents-skill" / ".agents"
    shutil.copytree(REPO_ROOT / ".agents", agents_dir)
    skill = agents_dir / "skills" / "volunteer" / "skill.md"
    skill.write_text(skill.read_text() + "\nBe brief.\n")
    app = build_app(
        r.settings.model_copy(update={"agents_dir": agents_dir}), runtime=FakeRuntime([]), jobs=InlineJobs()
    )
    async with app.router.lifespan_context(app):
        pass
    [row] = [x for x in r.new("skill.loaded") if x["entity_id"] == "volunteer"]
    assert (row["actor_id"], row["source"]) == ("system", "internal")


async def extraction_failed(r: R) -> None:
    ws = await r.env.ws()
    await r.env.upload("broken.pdf", b"%PDF-1.4 not a pdf")
    r.one("file.extraction_failed", "system", "internal", ws)


async def status_and_failure(r: R) -> None:
    ws = await r.env.ws()
    t1 = (await r.env.translators())[0]
    f = await r.env.upload("lease.txt", LEASE)
    gone = await r.env.upload("budget.txt", "Budget forty thousand.")
    r.location(gone).unlink()
    r.start = r.last_id()
    _, events = await r.env.ask(
        "When, and what about the budget?", [*happy(t1, f)[:7], step("verify", RuntimeError_("unavailable"), times=3)]
    )
    assert events[-1][1] == "error"
    assert r.new("question.status")[0]["actor_id"] == "system"
    r.one("question.failed", "system", "internal", ws)
    assert r.new("turn.failed")


async def interrupted(r: R) -> None:
    ws = await r.env.ws()
    session = await r.env.session()
    from twyf.contract.operations import AskInput
    from twyf.services import questions

    ctx = RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="t")
    await asyncio.to_thread(questions.start, ctx, AskInput(ws=ws, session_id=session, question="Left?"))
    app = build_app(r.settings, runtime=FakeRuntime([]), jobs=InlineJobs())
    async with app.router.lifespan_context(app):
        pass
    r.one("question.interrupted", "system", "internal", ws)


async def timed_out(r: R) -> None:
    from twyf.runtime.base import TurnRequest, TurnResult

    class Silent:
        name = "silent"
        capabilities = frozenset[str]()

        async def run_turn(self, request: TurnRequest) -> TurnResult:
            await asyncio.Event().wait()
            raise AssertionError

        async def cancel(self, turn_id: str) -> None:
            return None

    settings = r.settings.model_copy(update={"turn_timeout_s": 1, "max_turn_retries": 0})
    app = build_app(settings, runtime=Silent(), jobs=InlineJobs())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as c,
    ):
        env = Env(c, FakeRuntime([]), settings)
        await env.upload("lease.txt", LEASE)
        r.start = r.last_id()
        _, events = await env.ask("When?", [])
    assert events[-1][1] == "error"
    assert r.new("turn.timed_out")


async def queue_events(r: R) -> None:
    from twyf.runtime import queue as queue_module

    queue_module_waiting = queue_module.WAITING_S
    queue_module.WAITING_S, queue_module.WATCH_S = 0.1, 0.05
    try:
        app = build_app(
            r.settings.model_copy(update={"runtime": "queue"}), runtime=QueueRuntime(state.connect), jobs=InlineJobs()
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as c,
        ):
            env = Env(c, FakeRuntime([]), r.settings)
            ws = await env.ws()
            r.start = r.last_id()
            asked = asyncio.create_task(env.ask("Anything?", []))
            await asyncio.sleep(0.4)
            offer = (await c.post("/runtime/turns/claim", json={"worker": "w", "waitS": 2})).json()
            await c.post(
                f"/runtime/turns/{offer['turnId']}/submit",
                json={"leaseToken": offer["leaseToken"], "output": {"segments": [{"text": "No files yet."}]}},
            )
            await asyncio.wait_for(asked, 5)
        assert r.new("runtime.waiting")[0]["workspace_id"] == ws
        assert payload(r.new("turn.claimed")[0])["worker"] == "w"
    finally:
        queue_module.WAITING_S, queue_module.WATCH_S = queue_module_waiting, 1.0


CASES: dict[str, tuple[Case, set[str]]] = {
    "workspace": (workspace_crud, {"workspace.created", "workspace.renamed", "workspace.deleted"}),
    "upload from the UI": (upload_from_ui, {"file.uploaded", "file.extraction_completed", "file.indexed"}),
    "upload again": (upload_duplicate, {"file.upload_duplicate"}),
    "new version": (add_version, {"file.version_added", "file.ingest_started"}),
    "availability": (availability, {"file.missing", "file.changed", "file.restored"}),
    "deletes": (deletes, {"file.deleted", "agent.deleted", "note.deleted", "session.deleted"}),
    "renames and edits": (renames_and_edits, {"agent.renamed", "session.renamed", "note.edited"}),
    "agent through MCP": (create_agent_through_mcp, {"agent.created"}),
    "workspace agents": (workspace_creation_agents, {"agent.created"}),
    "user note": (add_user_note, {"note.created"}),
    "weights": (weights, {"note.weight_set"}),
    "session": (create_session, {"session.created"}),
    "ask": (ask, {"question.asked"}),
    "state changes": (state_changes, {"question.state_changed"}),
    "huddle": (
        huddle_events,
        {"huddle.broadcast", "huddle.member_joined", "huddle.file_assigned", "huddle.reading", "huddle.statement"},
    ),
    "assignment without note": (assignment_without_note, {"huddle.file_assigned"}),
    "turns": (turns, {"turn.queued", "turn.completed", "turn.failed"}),
    "search": (search, {"retrieval.searched"}),
    "quotes": (quotes, {"citation.created", "citation.rejected"}),
    "verification": (verification, {"verification.started", "verification.completed", "huddle.reopened"}),
    "answer": (answer, {"answer.written", "message.created", "question.completed"}),
    "cancel": (cancel, {"question.cancelled", "turn.cancelled"}),
    "direct chat": (direct_chat, {"translator.asked", "translator.replied"}),
    "definition edit": (definition_edit, {"definition.loaded"}),
    "config change": (config_change, {"config.changed"}),
    "demo": (demo_seeded, {"demo.seeded"}),
    "server start": (server_started, {"server.started"}),
    "skill change": (skill_change, {"skill.loaded"}),
    "parse failure": (extraction_failed, {"file.extraction_failed"}),
    "status and failure": (status_and_failure, {"question.status", "question.failed"}),
    "interrupted": (interrupted, {"question.interrupted"}),
    "timeout": (timed_out, {"turn.timed_out"}),
    "queue": (queue_events, {"runtime.waiting", "turn.claimed"}),
}


@pytest.mark.parametrize("name", list(CASES))
async def test_action_is_recorded(name: str, env: Env) -> None:
    case, _ = CASES[name]
    await case(R(env))


def test_every_event_type_is_tested(settings: Settings, conn: sqlite3.Connection) -> None:
    codes = {r[0] for r in conn.execute("SELECT code FROM event_types")}
    covered = set().union(*(types for _, types in CASES.values()))
    demo_source = inspect.getsource(test_demo.test_demo_recording)
    covered |= {c for c in codes if f'"{c}"' in demo_source}
    assert codes - covered == set()
