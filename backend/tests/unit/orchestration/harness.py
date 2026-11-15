"""Builds scripted turn outputs and runs questions through the engine with a FakeRuntime."""

import sqlite3
from dataclasses import dataclass
from typing import Any

from tests.conftest import upload
from twyf.config import Settings
from twyf.contract.events import AgentEvent
from twyf.contract.models import Workspace
from twyf.contract.operations import AskInput, CreateSessionInput
from twyf.db.repos import agents as agents_repo
from twyf.db.repos.events import wire_events
from twyf.orchestration.engine import Engine
from twyf.recording.broker import BROKER
from twyf.recording.context import RequestContext
from twyf.retrieval.hybrid import HybridRetriever
from twyf.runtime.fake import FakeRuntime, ScriptStep
from twyf.runtime.runner import TurnRunner
from twyf.services import questions, sessions, state

type Out = dict[str, Any]


def q(needle: str, quote: str | None = None) -> Out:
    """A new quote from the passage containing `needle`; the quote is `needle` unless given."""
    return {"passageId": {"$passage": needle}, "quote": quote or needle}


def reuse(needle: str) -> Out:
    return {"citationId": {"$citation": needle}}


def claim_id(needle: str) -> Out:
    return {"$claim": needle}


def plan(to: list[str], calls: list[Out] | None = None, text: str = "Who can help?") -> Out:
    return {"broadcastText": text, "broadcastTo": to, "directCalls": calls or []}


def volunteer(yes: bool, file_ids: list[str] | None = None) -> Out:
    return {"volunteer": yes, "reason": "Fits my speciality." if yes else "Not for me.", "fileIds": file_ids or []}


def assign(*pairs: tuple[str, list[str], str]) -> Out:
    return {"assignments": [{"agentId": a, "fileIds": f, "focus": focus} for a, f, focus in pairs]}


def work(statements: list[tuple[str, list[Out]]], notes: list[Out] | None = None, entities: list[Out] | None = None,
         searches: list[Out] | None = None) -> Out:  # fmt: skip
    return {
        "statements": [{"text": t, "quotes": qs} for t, qs in statements],
        "notes": notes or [], "entities": entities or [], "searches": searches or [],
    }  # fmt: skip


def review(decision: str, say: str = "", followups: list[tuple[str, str, list[str]]] | None = None) -> Out:
    return {
        "decision": decision,
        "say": say,
        "followups": [{"agentId": a, "focus": f, "fileIds": ids} for a, f, ids in followups or []],
    }


def quoted(ref: str, text: str, *citation_needles: str) -> Out:
    return {"ref": ref, "text": text, "kind": "quoted", "citationIds": [{"$citation": n} for n in citation_needles]}


def derived(ref: str, text: str, refs: list[str], expression: str | None = None, result: float | None = None) -> Out:
    out: Out = {"ref": ref, "text": text, "kind": "derived", "derivedFrom": refs}
    if expression is not None:
        out |= {"expression": expression, "statedResult": result}
    return out


def verdict(needle: str, kind: str, citation_needles: list[str], reason: str = "The passage states it.") -> Out:
    return {
        "claimId": {"$claim": needle}, "verdict": kind, "reason": reason,
        "citations": [{"citationId": {"$citation": c}, "supports": "full"} for c in citation_needles],
    }  # fmt: skip


def segments(*parts: tuple[str, list[str]]) -> Out:
    return {"segments": [{"text": t, "claimIds": [{"$claim": n} for n in needles]} for t, needles in parts]}


def step(turn_type: str, output: Out | Exception, agent: str | None = None, times: int = 1, **match: Any) -> ScriptStep:
    m: dict[str, Any] = {"turn_type": turn_type, **match}
    if agent is not None:
        m["agent_name"] = agent
    return ScriptStep(m, output, times)


@dataclass
class Harness:
    ws: Workspace
    ctx: RequestContext
    conn: sqlite3.Connection
    settings: Settings
    fake: FakeRuntime
    retriever: HybridRetriever

    @property
    def t1(self) -> str:
        return agents_repo.list(self.conn, self.ws.id, "translator")[0].id

    @property
    def t2(self) -> str:
        return agents_repo.list(self.conn, self.ws.id, "translator")[1].id

    def upload(self, name: str, text: str) -> str:
        return upload(self.ctx, self.ws.id, name, text.encode()).id

    def engine(self) -> Engine:
        return Engine(
            self.settings, state.connect, TurnRunner(self.fake, self.settings, state.connect), self.retriever, BROKER
        )

    async def ask(self, text: str, script: list[ScriptStep]) -> tuple[str, list[AgentEvent]]:
        self.fake.script = script
        session = sessions.create(self.ctx, CreateSessionInput(ws=self.ws.id, title="Test"))
        question_id = questions.start(self.ctx, AskInput(ws=self.ws.id, session_id=session.id, question=text))
        await self.engine().run(self.ctx, question_id)
        return question_id, [e for _, e in wire_events(self.conn, question_id)]

    def turn_inputs(self, turn_type: str) -> list[dict[str, Any]]:
        return [r.input for r in self.fake.requests if r.turn_type == turn_type]

    def state(self, question_id: str) -> str:
        return self.conn.execute("SELECT state FROM questions WHERE id = ?", (question_id,)).fetchone()[0]
