import sqlite3
from typing import Any

from tests.unit.orchestration.harness import (
    Harness,
    assign,
    derived,
    q,
    quoted,
    reuse,
    review,
    segments,
    step,
    verdict,
    volunteer,
    work,
)
from tests.unit.orchestration.harness import plan as plan_out
from twyf.orchestration.engine import NOT_READ
from twyf.runtime.base import RuntimeError_

PRICES = "The price is 29.00 per kg.\n\nCost of goods is 13.05 per kg.\n\nRent rises by 8% each year."
PRICE, COST, RENT = "price is 29.00 per kg", "Cost of goods is 13.05 per kg", "Rent rises by 8% each year"


def opening(h: Harness, f: str) -> list[Any]:
    return [
        step("plan", plan_out([h.t1])),
        step("volunteer", volunteer(True, [f]), "Translator 1"),
        step("assign", assign((h.t1, [f], "prices"))),
        step("work", work([("Price and cost.", [q("29.00", PRICE), q("13.05", COST)])]), "Translator 1"),
        step("review", review("settle", "Settled.")),
    ]


def two_claims(second: str = "Rent rises by 10% each year.") -> dict[str, Any]:
    return {"claims": [quoted("k1", "The price is 29.00 per kg.", "29.00"), quoted("k2", second, "13.05")]}


async def test_one_round_passes(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    question_id, events = await h.ask("What is the price?", [
        *opening(h, f),
        step("draft_claims", {"claims": [quoted("k1", "The price is 29.00 per kg.", "29.00")]}),
        step("verify", {"verdicts": [verdict("price is", "supported", ["29.00"])]}),
        step("write_answer", segments(("The price is 29.00 per kg.", ["price is"]))),
    ])  # fmt: skip
    assert [e.type for e in events].count("verify") == 1
    verdict_event = next(e for e in events if e.type == "verdict")
    assert verdict_event.passed and verdict_event.round == 1
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM verifications WHERE question_id = ? AND passed = 1", (question_id,)
        ).fetchone()[0]
        == 1
    )
    message = conn.execute(
        "SELECT id, text FROM messages WHERE question_id = ? AND role = 'assistant'", (question_id,)
    ).fetchone()
    assert message["text"] == "The price is 29.00 per kg [1]."
    assert conn.execute("SELECT COUNT(*) FROM message_claims WHERE message_id = ?", (message["id"],)).fetchone()[0] == 1
    completed = conn.execute(
        "SELECT payload FROM app_events WHERE question_id = ? AND event_type = 'question.completed'", (question_id,)
    ).fetchone()
    assert completed is not None and '"rounds": 1' in completed[0]


async def test_fail_then_pass_with_carried_verdict(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    question_id, events = await h.ask("What is the price and what does it cost?", [
        *opening(h, f),
        step("draft_claims", two_claims("Cost of goods is 13.05 per kg and falling.")),
        step("verify", {"verdicts": [
            verdict("price is", "supported", ["29.00"]),
            verdict("and falling", "partly_supported", ["13.05"], "Nothing says it is falling."),
        ]}),
        step("review", review("continue", "Check the cost again.", [(h.t1, "cost", [f])])),
        step("work", work([("The cost is 13.05.", [reuse("13.05")])]), "Translator 1"),
        step("review", review("settle", "Settled.")),
        step("draft_claims", two_claims("Cost of goods is 13.05 per kg.")),
        step("verify", {"verdicts": [verdict("Cost of goods", "supported", ["13.05"])]}),
        step("write_answer", segments(("The price is 29.00 per kg.", ["price is"]), ("Cost is 13.05 per kg.", ["Cost of goods"]))),
    ])  # fmt: skip
    kinds = [e.type for e in events]
    assert kinds.count("verify") == 2 and kinds.count("verdict") == 2 and kinds.count("rehuddle") == 1
    rehuddle = next(e for e in events if e.type == "rehuddle")
    first_verdict = next(e for e in events if e.type == "verdict")
    assert rehuddle.round == 2 and rehuddle.reason == "Nothing says it is falling."
    assert rehuddle.claim_ids == [v.claim_id for v in first_verdict.verdicts if v.verdict != "supported"]
    assert kinds.index("rehuddle") == kinds.index("verdict") + 1
    verify_inputs = h.turn_inputs("verify")
    assert len(verify_inputs[1]["claims"]) == 1
    second = [e for e in events if e.type == "verdict"][1]
    assert second.passed and len(second.verdicts) == 2
    carried = conn.execute(
        "SELECT COUNT(*) FROM verdicts v JOIN verifications x ON x.id = v.verification_id"
        " WHERE x.question_id = ? AND v.carried_from IS NOT NULL", (question_id,)).fetchone()[0]  # fmt: skip
    assert carried == 1
    assert events[-1].type == "answer" and h.state(question_id) == "answered"


async def test_three_failures_give_a_partial_answer(harness: Any) -> None:
    h: Harness = harness
    h.settings.max_verify_rounds = 3  # the script runs three rounds; the default is lower
    f = h.upload("prices.txt", PRICES)
    failing = [
        step(
            "verify",
            {
                "verdicts": [
                    verdict("price is", "supported", ["29.00"]),
                    verdict("10%", "unsupported", ["13.05"], "The file says 8%."),
                ]
            },
        ),
    ]

    def again() -> list[Any]:
        return [
            step("review", review("continue", "Again.", [(h.t1, "rent", [f])])),
            step("work", work([("Rent rises by 8%.", [q("Rent rises", RENT)])]), "Translator 1"),
            step("review", review("settle", "Settled.")),
            step("draft_claims", two_claims()),
            # Identical claims: both verdicts are carried, so the verifier is not asked again.
        ]

    question_id, events = await h.ask("How fast does rent rise?", [
        *opening(h, f), step("draft_claims", two_claims()), *failing, *again(), *again(),
        step("write_answer", segments(("The price is 29.00 per kg.", ["price is"]))),
    ])  # fmt: skip
    kinds = [e.type for e in events]
    assert kinds.count("verify") == 3 and kinds.count("rehuddle") == 2
    answer = events[-1]
    assert answer.type == "answer" and answer.text == "The price is 29.00 per kg [1]."
    assert answer.unverified is not None and [(u.text, u.reason) for u in answer.unverified] == [
        ("Rent rises by 10% each year.", "The file says 8%.")
    ]
    assert h.state(question_id) == "answered_partial"
    assert h.fake.unused() == []
    assert len(h.turn_inputs("verify")) == 1


async def test_mechanical_failure(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    bad = derived("k3", "The margin is 60%.", ["k1", "k2"], "1 - 13.05 / 29.00", 0.60)
    good = derived("k3", "The margin is 55%.", ["k1", "k2"], "1 - 13.05 / 29.00", 0.55)
    claims = [
        quoted("k1", "The price is 29.00 per kg.", "29.00"),
        quoted("k2", "Cost of goods is 13.05 per kg.", "13.05"),
    ]
    question_id, events = await h.ask("What is the margin?", [
        *opening(h, f),
        step("draft_claims", {"claims": [*claims, bad]}),
        step("verify", {"verdicts": [verdict("price is", "supported", ["29.00"]), verdict("Cost of goods", "supported", ["13.05"])]}),
        step("review", review("settle", "Fix the sum.")),
        step("draft_claims", {"claims": [*claims, good]}),
        step("verify", {"verdicts": [verdict("margin is 55", "supported", ["29.00", "13.05"])]}),
        step("write_answer", segments(("The margin is 55%.", ["margin is 55"]))),
    ])  # fmt: skip
    first_verify = h.turn_inputs("verify")[0]
    assert all("60%" not in c["text"] for c in first_verify["claims"])
    first = next(e for e in events if e.type == "verdict")
    assert not first.passed and [v.verdict for v in first.verdicts] == ["supported", "supported", "mechanical_fail"]
    assert h.state(question_id) == "answered"


async def test_zero_claims(harness: Any, conn: sqlite3.Connection) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    question_id, events = await h.ask("What is our supplier's phone number?", [
        *opening(h, f),
        step("draft_claims", {"claims": []}),
        step("write_answer", {"segments": [{"text": "The files do not give a phone number."}]}),
    ])  # fmt: skip
    kinds = [e.type for e in events]
    assert "verify" not in kinds and "leave" in kinds and kinds[-1] == "answer"
    assert events[-1].type == "answer" and events[-1].citations == []
    assert not h.turn_inputs("verify")
    assert h.turn_inputs("write_answer")[0]["mode"] == "nothing_found"
    assert h.state(question_id) == "answered"


async def test_answer_fallback(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    _, events = await h.ask("What is the price?", [
        *opening(h, f),
        step("draft_claims", {"claims": [quoted("k1", "The price is 29.00 per kg.", "29.00")]}),
        step("verify", {"verdicts": [verdict("price is", "supported", ["29.00"])]}),
        step("write_answer", RuntimeError_("unavailable"), times=3),
    ])  # fmt: skip
    answer = events[-1]
    assert answer.type == "answer" and answer.text == "The price is 29.00 per kg [1]."
    assert len(answer.citations) == 1


async def test_no_files(harness: Any) -> None:
    h: Harness = harness
    question_id, events = await h.ask("Anything?", [
        step("write_answer", {"segments": [{"text": "There are no files in this workspace yet."}]}),
    ])  # fmt: skip
    assert [e.type for e in events] == ["started", "answer"]
    assert [r.turn_type for r in h.fake.requests] == ["write_answer"]
    assert h.state(question_id) == "answered"


async def test_unreadable_file_is_named_after_the_answer(harness: Any) -> None:
    h: Harness = harness
    f = h.upload("prices.txt", PRICES)
    h.upload("scan.txt", " \n")
    _, events = await h.ask("What is the price?", [
        *opening(h, f),
        step("draft_claims", {"claims": [quoted("k1", "The price is 29.00 per kg.", "29.00")]}),
        step("verify", {"verdicts": [verdict("price is", "supported", ["29.00"])]}),
        step("write_answer", segments(("The price is 29.00 per kg.", ["price is"]))),
    ])  # fmt: skip
    assert [f["name"] for f in h.turn_inputs("plan")[0]["files"]] == ["prices.txt"]
    assert events[-1].text == f"The price is 29.00 per kg [1].\n\n{NOT_READ} scan.txt."


async def test_only_unreadable_files(harness: Any) -> None:
    h: Harness = harness
    h.upload("scan.txt", " \n")
    question_id, events = await h.ask("Anything?", [
        step("write_answer", {"segments": [{"text": "There are no files in this workspace yet."}]}),
    ])  # fmt: skip
    assert events[-1].text == f"{NOT_READ} scan.txt."
    assert h.state(question_id) == "answered"
