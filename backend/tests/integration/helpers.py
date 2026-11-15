"""Shared helpers for the HTTP integration tests."""

import asyncio
import json
import sqlite3
from typing import Any

import httpx

from tests.unit.orchestration.harness import assign, q, quoted, review, segments, step, verdict, volunteer, work
from tests.unit.orchestration.harness import plan as plan_out
from twyf.config import Settings
from twyf.db.connection import connect
from twyf.runtime.base import TurnRequest, TurnResult
from twyf.runtime.fake import FakeRuntime, ScriptStep
from twyf.services import state

LEASE = "The lease ends on 30 June 2029.\n\nRent rises by 8% each year."
ENDS = "ends on 30 June 2029"


def parse_sse(text: str) -> list[tuple[int, str, dict[str, Any]]]:
    events: list[tuple[int, str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            events.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return events


class Env:
    def __init__(self, client: httpx.AsyncClient, fake: FakeRuntime, settings: Settings) -> None:
        self.client, self.fake, self.settings = client, fake, settings

    async def ws(self) -> str:
        return (await self.client.get("/workspaces")).json()[0]["id"]

    async def translators(self) -> list[str]:
        return [a["id"] for a in (await self.client.get(f"/workspaces/{await self.ws()}/agents")).json()]

    async def upload(self, name: str, text: str) -> str:
        ws = await self.ws()
        return (await self.client.post(f"/workspaces/{ws}/files", files={"file": (name, text.encode())})).json()["id"]

    async def session(self) -> str:
        return (await self.client.post(f"/workspaces/{await self.ws()}/sessions", json={"title": "S"})).json()["id"]

    async def ask(
        self, question: str, script: list[ScriptStep], session: str | None = None
    ) -> tuple[httpx.Response, list[tuple[int, str, dict[str, Any]]]]:
        self.fake.script = script
        sid = session or await self.session()
        response = await self.client.post(
            f"/workspaces/{await self.ws()}/sessions/{sid}/questions", json={"question": question}
        )
        events = parse_sse(response.text) if response.status_code == 200 else []
        if events:
            await state.tasks().wait(events[0][2]["questionId"])  # Complete runs just after the final event
        return response, events

    def db(self) -> sqlite3.Connection:
        return connect(self.settings.data_dir / "twyf.db")


def happy(t1: str, f: str) -> list[ScriptStep]:
    return [
        step("plan", plan_out([t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("volunteer", volunteer(False), "Translator 2"),
        step("assign", assign((t1, [f], "end date"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", ENDS)])]), "Translator 1"),
        step("review", review("settle", "We have it.")),
        step("draft_claims", {"claims": [quoted("k1", "The lease ends on 30 June 2029.", "30 June")]}),
        step("verify", {"verdicts": [verdict("lease ends", "supported", ["30 June"])]}),
        step("write_answer", segments(("The lease ends on 30 June 2029.", ["lease ends"]))),
    ]


class Gate:
    """A runtime whose turns wait until released, so a question can be caught while running."""

    name = "gate"
    capabilities = frozenset({"vision"})

    def __init__(self, inner: FakeRuntime) -> None:
        self.inner = inner
        self.release = asyncio.Event()
        self.waiting = asyncio.Event()
        self.cancelled: list[str] = []

    async def run_turn(self, request: TurnRequest) -> TurnResult:
        if request.turn_type == "work":
            self.waiting.set()
            await self.release.wait()
        return await self.inner.run_turn(request)

    async def cancel(self, turn_id: str) -> None:
        self.cancelled.append(turn_id)
