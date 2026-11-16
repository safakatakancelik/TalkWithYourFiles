import json
from pathlib import Path

import httpx

from tests.conftest import DEMO_FIXTURES
from twyf.evals.runner import EvalResult, load_cases, outcome_of, run_case, write_report
from twyf.runtime.fake import FakeRuntime


def test_cases_load() -> None:
    cases = {c.name: c for c in load_cases()}
    assert {"demo", "lease end", "paid leave", "no phone number", "injection", "demo with weights"} == set(cases)
    assert cases["no phone number"].expect_outcome == "nothing_found"


async def test_run_case_demo(demo: str, client: httpx.AsyncClient, fake: FakeRuntime, tmp_path: Path) -> None:
    fake.script = FakeRuntime.from_file(DEMO_FIXTURES / "script.json").script
    [case] = [c for c in load_cases() if c.name == "demo"]
    result = await run_case(client, case)
    assert result.passed, result.checks
    assert all(result.checks.values()) and len(result.checks) == 1 + 3 + 4
    assert (result.outcome, result.rounds) == ("answer", 2)
    report = tmp_path / "report.json"
    write_report([result], report)
    assert json.loads(report.read_text())["results"][0]["name"] == "demo"


def test_outcomes() -> None:
    assert outcome_of([{"type": "error"}]) == "error"
    assert outcome_of([{"type": "answer", "citations": [], "unverified": [{"text": "x"}]}]) == "partial"
    assert outcome_of([{"type": "answer", "citations": []}]) == "nothing_found"
    assert outcome_of([{"type": "answer", "citations": [{"n": 1}]}]) == "answer"
    assert outcome_of([]) == "error"
    assert EvalResult.model_fields.keys() >= {"outcome", "checks", "rounds", "claims", "verdicts", "seconds"}
