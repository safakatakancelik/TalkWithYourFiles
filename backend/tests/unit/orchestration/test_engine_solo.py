from typing import Any

from tests.unit.orchestration.harness import (
    Harness,
    assign,
    q,
    quoted,
    review,
    segments,
    step,
    verdict,
    volunteer,
    work,
)
from tests.unit.orchestration.harness import plan as plan_out
from twyf.contract.events import AgentEvent

LEASE = "The lease ends on 30 June 2029.\n\nRent rises by 8% each year."
ENDS = "ends on 30 June 2029"


def turn_types(h: Harness) -> list[str]:
    return [r.turn_type for r in h.fake.requests]


def claims_to_answer() -> list[Any]:
    return [
        step("draft_claims", {"claims": [quoted("k1", "The lease ends on 30 June 2029.", "30 June")]}),
        step("verify", {"verdicts": [verdict("lease ends", "supported", ["30 June"])]}),
        step("write_answer", segments(("The lease ends on 30 June 2029.", ["lease ends"]))),
    ]


async def test_one_translator_runs_four_turns(solo_harness: Any) -> None:
    h: Harness = solo_harness
    f = h.upload("lease.txt", LEASE)
    question_id, events = await h.ask("When does the lease end?", [
        step("work", work([("It ends on 30 June 2029.", [q("30 June", ENDS)])]), "Translator"),
        *claims_to_answer(),
    ])  # fmt: skip
    assert turn_types(h) == ["work", "draft_claims", "verify", "write_answer"]
    assert h.fake.unused() == []
    assert h.state(question_id) == "answered"
    joins = [e for e in events if e.type == "join"]
    assigns = [e for e in events if e.type == "assign"]
    assert [(j.agent_id, j.how) for j in joins] == [(h.t1, "called")]
    assert [(a.agent_id, a.file_id) for a in assigns] == [(h.t1, f)]
    assert not any(e.type == "broadcast" for e in events)
    answer: AgentEvent = events[-1]
    assert answer.type == "answer" and answer.text == "The lease ends on 30 June 2029 [1]."


async def test_one_translator_gets_every_ready_file(solo_harness: Any) -> None:
    h: Harness = solo_harness
    a = h.upload("lease.txt", LEASE)
    b = h.upload("rent.txt", "The deposit is 2000 euros.")
    _, events = await h.ask("When does the lease end?", [
        step("work", work([("It ends on 30 June 2029.", [q("30 June", ENDS)])]), "Translator"),
        *claims_to_answer(),
    ])  # fmt: skip
    assert sorted(e.file_id for e in events if e.type == "assign") == sorted([a, b])


async def test_two_translators_run_the_full_huddle(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("lease.txt", LEASE)
    question_id, _ = await h.ask("When does the lease end?", [
        step("plan", plan_out([h.t1, h.t2])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("volunteer", volunteer(False), "Translator 2"),
        step("assign", assign((h.t1, [f], "end date"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", ENDS)])]), "Translator 1"),
        step("review", review("settle", "We have it.")),
        *claims_to_answer(),
    ])  # fmt: skip
    assert turn_types(h) == [
        "plan", "volunteer", "volunteer", "assign", "work", "review", "draft_claims", "verify", "write_answer",
    ]  # fmt: skip
    assert h.state(question_id) == "answered"
