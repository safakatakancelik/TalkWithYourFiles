"""The evaluation set (07-test-plan.md section 8): questions with expectations, run against a live API."""

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from twyf import clock

EVALS = Path(__file__).resolve().parents[3] / "evals"
DEMO_WORKSPACE = "demo"


class EvalCase(BaseModel):
    name: str
    workspace: str  # a folder under evals/workspaces/, or "demo" for the seeded demo workspace
    question: str
    must_state: list[str] = Field(default_factory=list[str])  # regular expressions
    must_cite: list[str] = Field(default_factory=list[str])  # file names
    must_not_state: list[str] = Field(default_factory=list[str])
    expect_outcome: str = "answer"  # 'answer' | 'partial' | 'nothing_found' | 'error'
    weights: dict[str, str] = Field(default_factory=dict[str, str])  # note id -> weight, set before asking
    user_notes: list[dict[str, str]] = Field(default_factory=list[dict[str, str]])  # {file, text, weight}


class EvalResult(BaseModel):
    name: str
    outcome: str
    checks: dict[str, bool]
    passed: bool
    rounds: int
    claims: int
    verdicts: list[dict[str, Any]]
    input_tokens: int | None = None
    output_tokens: int | None = None
    seconds: float
    answer: str = ""


def load_cases(path: Path = EVALS / "cases.json") -> list[EvalCase]:
    return [EvalCase.model_validate(c) for c in json.loads(path.read_text())]


def parse_events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def _workspace(client: httpx.AsyncClient, case: EvalCase) -> tuple[str, dict[str, str]]:
    """The workspace id and its files by name."""
    if case.workspace == DEMO_WORKSPACE:
        ws = DEMO_WORKSPACE
    else:
        ws = (await client.post("/workspaces", json={"name": f"eval: {case.name}"})).json()["id"]
        for path in sorted((EVALS / "workspaces" / case.workspace).iterdir()):
            await client.post(f"/workspaces/{ws}/files", files={"file": (path.name, path.read_bytes())})
    response = await client.get(f"/workspaces/{ws}/files")
    response.raise_for_status()
    return ws, {f["name"]: f["id"] for f in response.json()}


def outcome_of(events: list[dict[str, Any]]) -> str:
    last = events[-1] if events else {"type": "error"}
    if last["type"] != "answer":
        return "error" if last["type"] == "error" else last["type"]
    if last.get("unverified"):
        return "partial"
    return "answer" if last.get("citations") else "nothing_found"


async def run_case(client: httpx.AsyncClient, case: EvalCase) -> EvalResult:
    """Asks the case's question and checks each expectation. `client` has base URL `<api>/api/v1`."""
    started = time.monotonic()
    ws, files = await _workspace(client, case)
    for note_id, weight in case.weights.items():
        await client.post(f"/workspaces/{ws}/notes/weight", json={"noteIds": [note_id], "weight": weight})
    for note in case.user_notes:
        made = (
            await client.post(
                f"/workspaces/{ws}/notes", json={"fileId": files.get(note["file"], note["file"]), "text": note["text"]}
            )
        ).json()
        if note.get("weight"):
            await client.post(
                f"/workspaces/{ws}/notes/weight", json={"noteIds": [made["id"]], "weight": note["weight"]}
            )
    session = (await client.post(f"/workspaces/{ws}/sessions", json={"title": f"eval: {case.name}"})).json()["id"]
    response = await client.post(
        f"/workspaces/{ws}/sessions/{session}/questions", json={"question": case.question}, timeout=None
    )
    events = parse_events(response.text)
    empty: dict[str, Any] = {"text": "", "citations": []}
    answer: dict[str, Any] = next((e for e in events if e["type"] == "answer"), empty)
    text = str(answer["text"])
    citations: list[dict[str, Any]] = answer.get("citations", [])
    cited = {c.get("fileName") for c in citations}
    checks: dict[str, bool] = {f"outcome is {case.expect_outcome}": outcome_of(events) == case.expect_outcome}
    checks |= {f"states /{p}/": re.search(p, text, re.IGNORECASE) is not None for p in case.must_state}
    checks |= {f"cites {name}": name in cited for name in case.must_cite}
    checks |= {f"does not state /{p}/": re.search(p, text, re.IGNORECASE) is None for p in case.must_not_state}
    question_id = events[0].get("questionId") if events else None
    completed: dict[str, Any] = {}
    if question_id:
        rows = (await client.get("/events", params={"question": question_id, "type": "question.completed"})).json()
        completed = rows[0]["payload"] if rows else {}
    verifies = [e for e in events if e["type"] == "verify"]
    return EvalResult(
        name=case.name, outcome=outcome_of(events), checks=checks, passed=all(checks.values()),
        rounds=len(verifies), claims=sum(len(v["claims"]) for v in verifies),
        verdicts=[v for e in events if e["type"] == "verdict" for v in e["verdicts"]],
        input_tokens=completed.get("input_tokens"), output_tokens=completed.get("output_tokens"),
        seconds=round(time.monotonic() - started, 2), answer=text,
    )  # fmt: skip


def write_report(results: list[EvalResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"written_at": clock.now(), "results": [r.model_dump(mode="json") for r in results]}
    path.write_text(json.dumps(report, indent=2) + "\n")


async def run_all(api_url: str, runtime: str | None, names: list[str] | None) -> int:
    """Runs the cases against the API at `api_url` and writes evals/reports/<time>.json. 0 when all pass."""
    cases = [c for c in load_cases() if not names or c.name in names]
    async with httpx.AsyncClient(base_url=api_url + "/api/v1", timeout=None) as client:
        health = (await client.get("/health")).json()
        if runtime is not None and health.get("runtime") != runtime:
            print(f"the server runs the {health.get('runtime')} runtime, not {runtime}")
            return 2
        results = [await run_case(client, case) for case in cases]
    path = EVALS / "reports" / f"{clock.now().replace(':', '-')}.json"
    write_report(results, path)
    for r in results:
        print(f"{'pass' if r.passed else 'FAIL'}  {r.name}  ({r.outcome}, {r.rounds} rounds, {r.seconds}s)")
        for check, ok in r.checks.items():
            if not ok:
                print(f"      not met: {check}")
    print(f"report: {path}")
    return 0 if all(r.passed for r in results) else 1
