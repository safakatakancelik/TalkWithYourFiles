import sqlite3
from typing import Any

from tests.unit.orchestration.harness import (
    Harness,
    assign,
    derived,
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
from twyf.orchestration.engine import named

LEASE = "The lease ends on 30 June 2029.\n\nRent rises by 8% each year."


def types(events: list[AgentEvent]) -> list[str]:
    return [e.type for e in events]


def tail(h: Harness, needle: str = "30 June") -> list[Any]:
    """Settle, draft one quoted claim, verify it, write the answer."""
    return [
        step("review", review("settle", "We have it.")),
        step("draft_claims", {"claims": [quoted("k1", "The lease ends on 30 June 2029.", needle)]}),
        step("verify", {"verdicts": [verdict("lease ends", "supported", [needle])]}),
        step("write_answer", segments(("The lease ends on 30 June 2029.", ["lease ends"]))),
    ]


async def test_broadcast_to_all_with_two_volunteers(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("lease.txt", LEASE)
    question_id, events = await h.ask("When does the lease end?", [
        step("plan", plan_out([h.t1, h.t2])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("volunteer", volunteer(True, [f]), "Translator 2"),
        step("assign", assign((h.t1, [f], "end date"), (h.t2, [f], "rent"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", "ends on 30 June 2029")])],
                          notes=[{"fileId": f, "kind": "finding", "text": "Ends 2029.", "quotes": [q("30 June", "30 June 2029")]}]),
             "Translator 1"),
        step("work", work([("Rent rises by 8% a year.", [q("Rent rises", "Rent rises by 8% each year")])]), "Translator 2"),
        *tail(h),
    ])  # fmt: skip
    assert types(events) == [
        "started",
        "broadcast",
        "join",
        "join",
        "assign",
        "assign",
        "reading",
        "reading",
        "say",
        "note",
        "say",
        "say",
        "verify",
        "verdict",
        "leave",
        "answer",
    ] or sorted(types(events)[6:11]) == ["note", "reading", "reading", "say", "say"]
    assert types(events)[:6] == ["started", "broadcast", "join", "join", "assign", "assign"]
    assert types(events)[-5:] == ["say", "verify", "verdict", "leave", "answer"]
    joins = [e for e in events if e.type == "join"]
    assert [(j.agent_id, j.how) for j in joins] == [(h.t1, "volunteered"), (h.t2, "volunteered")]
    answer = events[-1]
    assert answer.type == "answer" and answer.text == "The lease ends on 30 June 2029 [1]."
    assert h.state(question_id) == "answered"
    assert h.fake.unused() == []


async def test_direct_call(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("lease.txt", LEASE)
    _, events = await h.ask("When does the lease end?", [
        step("plan", plan_out([], [{"agentId": h.t2, "fileIds": [f], "reason": "Knows leases"}])),
        step("assign", assign((h.t2, [f], "end date"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", "ends on 30 June 2029")])]), "Translator 2"),
        *tail(h),
    ])  # fmt: skip
    assert "broadcast" not in types(events)
    [join] = [e for e in events if e.type == "join"]
    assert (join.agent_id, join.how) == (h.t2, "called")


async def test_followup_calls_a_new_translator(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    f = h.upload("lease.txt", LEASE)
    question_id, events = await h.ask("When does the lease end and what about rent?", [
        step("plan", plan_out([h.t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("assign", assign((h.t1, [f], "end date"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", "ends on 30 June 2029")])]), "Translator 1"),
        step("review", review("continue", "Rent too, please.", [(h.t2, "rent", [f])])),
        step("work", work([("Rent rises by 8%.", [q("Rent rises", "Rent rises by 8% each year")])]), "Translator 2"),
        *tail(h),
    ])  # fmt: skip
    joins = [(e.agent_id, e.how) for e in events if e.type == "join"]
    assert joins == [(h.t1, "volunteered"), (h.t2, "called")]
    says = [e for e in events if e.type == "say"]
    assert says[1].agent_id == "orchestrator" and says[1].text == "Rent too, please."
    [leave] = [e for e in events if e.type == "leave"]
    assert sorted(leave.agent_ids) == sorted([h.t1, h.t2])
    assert conn.execute("SELECT COUNT(*) FROM assignments WHERE question_id = ?", (question_id,)).fetchone()[0] == 2


async def test_search_loop_is_limited(harness: Any) -> None:
    h: Harness = harness
    h.settings.searches_per_turn = 2
    f = h.upload("lease.txt", LEASE)
    search = {"fileId": f, "query": "rent"}
    _, events = await h.ask("When does the lease end?", [
        step("plan", plan_out([h.t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("assign", assign((h.t1, [f], "end date"))),
        step("work", work([("Looking.", [q("30 June", "ends on 30 June 2029")])], searches=[search]), "Translator 1", searchesLeft=2),
        step("work", work([("Looking.", [q("30 June", "ends on 30 June 2029")])], searches=[search]), "Translator 1", searchesLeft=1),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", "ends on 30 June 2029")])]), "Translator 1", searchesLeft=0),
        *tail(h),
    ])  # fmt: skip
    works = h.turn_inputs("work")
    assert [w["searchesLeft"] for w in works] == [2, 1, 0]
    assert len([e for e in events if e.type == "say" and e.agent_id == h.t1]) == 1


async def test_missing_file_is_in_no_turn_input(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    f = h.upload("lease.txt", LEASE)
    gone = h.upload("budget.txt", "The budget is forty thousand.")
    location = conn.execute("SELECT location FROM v_files WHERE id = ?", (gone,)).fetchone()[0]
    (h.settings.data_dir / location).unlink()
    _, events = await h.ask("When does the lease end, and what does the budget say?", [
        step("plan", plan_out([h.t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("assign", assign((h.t1, [f], "end date"))),
        step("work", work([("It ends on 30 June 2029.", [q("30 June", "ends on 30 June 2029")])]), "Translator 1"),
        *tail(h),
    ])  # fmt: skip
    assert events[1].type == "status" and "budget.txt" in events[1].text
    assert all(gone not in str(r.input) for r in h.fake.requests)


def test_named_files_and_agents(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    lease = h.upload("Office-Lease.pdf", "x")
    h.upload("budget.txt", "y")
    files, agents = named(conn, h.ws.id, "What does the office-lease say? Ask translator 2.")
    assert files == [lease] and agents == [h.t2]
    assert named(conn, h.ws.id, "Nothing named here.") == ([], [])


async def test_derived_claims_flow(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", "The price is 29.00 per kg.\n\nCost of goods is 13.05 per kg.")
    _, events = await h.ask("What is our margin?", [
        step("plan", plan_out([h.t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("assign", assign((h.t1, [f], "margin"))),
        step("work", work([("Price 29.00, cost 13.05.", [q("29.00", "price is 29.00 per kg"), q("13.05", "Cost of goods is 13.05 per kg")])]), "Translator 1"),
        step("review", review("settle", "Settled.")),
        step("draft_claims", {"claims": [
            quoted("k1", "The price is 29.00 per kg.", "29.00"), quoted("k2", "Cost of goods is 13.05 per kg.", "13.05"),
            derived("k3", "The margin is 55.0%.", ["k1", "k2"], "1 - 13.05 / 29.00", 0.55),
        ]}),
        step("verify", {"verdicts": [
            verdict("price is", "supported", ["29.00"]), verdict("Cost of goods", "supported", ["13.05"]),
            verdict("margin is", "supported", ["29.00", "13.05"]),
        ]}),
        step("write_answer", segments(("The margin is 55.0%.", ["margin is"]))),
    ])  # fmt: skip
    verify = next(e for e in events if e.type == "verify")
    assert [c.kind for c in verify.claims] == ["quoted", "quoted", "derived"]
    assert verify.claims[2].citations == [1, 2] and verify.claims[2].calculation == "1 - 13.05 / 29.00"
    assert events[-1].type == "answer" and events[-1].text == "The margin is 55.0% [1][2]."
