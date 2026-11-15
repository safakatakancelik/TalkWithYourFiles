import sqlite3

import pytest

from tests.conftest import cite, upload
from twyf.contract.models import Workspace
from twyf.contract.turns import ClaimOut, ClaimRef, Segment
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import turns as turns_repo
from twyf.orchestration.arithmetic import ArithmeticRejected, evaluate, within_tolerance
from twyf.orchestration.claims import (
    assemble_answer,
    fallback_answer,
    passes,
    store_claims,
    validate_claims,
    validate_segments,
)
from twyf.recording.context import RequestContext

NOW = "2026-11-16T00:00:00.000Z"


def test_arithmetic() -> None:
    for expression, stated in (
        ("1 - (13.05 + 7.60 * 0.08) / 29.00", 0.529),
        ("(13.05 + 7.60 * 0.08) / (1 - 0.55)", 30.35),
        ("7.60 * 0.08 / 13.05", 0.047),
    ):
        assert within_tolerance(evaluate(expression), stated)
    assert evaluate("round(abs(-2.345), 2) + min(1, 2) + max(1, 2) - 2 ** 2 + +1") == pytest.approx(2.35)
    assert not within_tolerance(0.529, 0.6)
    for bad in ("x + 1", "(1).real", "open('f')", "int(2)", "1 / 0", "'a'", "True + 1", "1 % 2", "2 ** 1000",
                "max()", "round(1, ndigits=2)", "1 +", "9" * 400):  # fmt: skip
        with pytest.raises(ArithmeticRejected):
            evaluate(bad)


def _claim(ref: str, text: str, kind: str = "quoted", **kw: object) -> ClaimOut:
    return ClaimOut.model_validate({"ref": ref, "text": text, "kind": kind, **kw})


def test_claim_rules() -> None:
    known = {"c_1", "c_2"}
    assert validate_claims([_claim("k1", "A", citationIds=["c_1"])], known) == []
    assert validate_claims([_claim("k1", "A")], known) == ["quoted claim k1 needs at least one citation"]
    assert "not a citation" in validate_claims([_claim("k1", "A", citationIds=["c_9"])], known)[0]
    good = [_claim("k1", "A", citationIds=["c_1"]), _claim("k2", "B", "derived", derivedFrom=["k1"])]
    assert validate_claims(good, known) == []
    assert "at least one derived_from" in validate_claims([_claim("k1", "A", "derived")], known)[0]
    assert "unknown ref k9" in validate_claims([_claim("k1", "A", "derived", derivedFrom=["k9"])], known)[0]
    cycle = [_claim("k1", "A", "derived", derivedFrom=["k2"]), _claim("k2", "B", "derived", derivedFrom=["k1"])]
    assert sum("cycle" in e for e in validate_claims(cycle, known)) == 2
    diamond = [
        _claim("k1", "A", citationIds=["c_1"]), _claim("k2", "B", "derived", derivedFrom=["k1"]),
        _claim("k3", "C", "derived", derivedFrom=["k1"]), _claim("k4", "D", "derived", derivedFrom=["k2", "k3"]),
    ]  # fmt: skip
    assert validate_claims(diamond, known) == []
    assert "unique" in validate_claims([_claim("k1", "A", citationIds=["c_1"])] * 2, known)[0]


@pytest.fixture
def question(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> dict[str, str]:
    a = upload(ctx, ws.id, "a.txt", b"The price is 29.00 per unit. Cost is 13.05 per unit.")
    orchestrator = agents_repo.builtin(conn, ws.id, "orchestrator")
    c1 = cite(conn, ctx, ws.id, a.id, "The price is 29.00 per unit", orchestrator.id)
    c2 = cite(conn, ctx, ws.id, a.id, "Cost is 13.05 per unit", orchestrator.id)
    dv = conn.execute(
        "SELECT id FROM agent_definition_versions WHERE definition_id = ?", (orchestrator.definition_id,)
    ).fetchone()[0]
    with transaction(conn):
        conn.execute("INSERT INTO sessions VALUES ('s_1', ?, ?, ?, NULL)", (ws.id, NOW, NOW))
        conn.execute(
            "INSERT INTO questions (id, workspace_id, session_id, state, max_rounds, config_version_id, runtime, started_at)"
            " VALUES ('q_1', ?, 's_1', 'drafting', 3, (SELECT MAX(id) FROM config_versions), 'fake', ?)", (ws.id, NOW))  # fmt: skip
        for r in (1, 2):
            conn.execute(
                "INSERT INTO huddle_rounds VALUES (?, ?, 'q_1', ?, 'initial', ?, NULL)", (f"r_{r}", ws.id, r, NOW)
            )
            turns_repo.insert(
                conn, turn_id=f"t_{r}", workspace_id=ws.id, question_id="q_1", round_id=f"r_{r}", agent_id=orchestrator.id,
                agent_version_id=orchestrator.agent_version_id, definition_version_id=dv, turn_type="draft_claims",
                attempt=1, retry_of=None, runtime="fake", system_prompt="s", input={},
            )  # fmt: skip
    return {"c1": c1, "c2": c2, "orchestrator": orchestrator.id}


def _store(conn: sqlite3.Connection, ctx: RequestContext, round_no: int, claims: list[ClaimOut]):
    with transaction(conn):
        return store_claims(
            conn, ctx, question_id="q_1", round_id=f"r_{round_no}", turn_id=f"t_{round_no}", claims=claims
        )


def test_store_claims(conn: sqlite3.Connection, ctx: RequestContext, question: dict[str, str]) -> None:
    c1, c2 = question["c1"], question["c2"]
    rows = _store(conn, ctx, 1, [
        _claim("k3", "Margin is 55.0%.", "derived", derivedFrom=["k1", "k2"], expression="1 - 13.05 / 29.00", statedResult=0.55),
        _claim("k1", "Price is 29.00.", citationIds=[c1]),
        _claim("k2", "Cost is 13.05.", citationIds=[c2, c2]),
        _claim("k4", "Margin is 60%.", "derived", derivedFrom=["k3"], expression="1 - 13.05 / 29.00", statedResult=0.6),
        _claim("k5", "Bad.", "derived", derivedFrom=["k1"], expression="x * 2", statedResult=1.0),
    ])  # fmt: skip
    by_ref = {r.ref: r for r in rows}
    assert [r.ref for r in rows] == ["k1", "k2", "k3", "k4", "k5"]
    assert by_ref["k2"].citation_ids == (c2,)
    assert by_ref["k3"].citation_ids == (c1, c2) and by_ref["k4"].citation_ids == (c1, c2)
    assert by_ref["k3"].input_ids == (by_ref["k1"].id, by_ref["k2"].id)
    assert by_ref["k3"].arithmetic_error is None and by_ref["k3"].computed_result == pytest.approx(0.55, abs=0.001)
    assert by_ref["k4"].arithmetic_error is not None and "0.6" in by_ref["k4"].arithmetic_error
    assert by_ref["k5"].arithmetic_error is not None and by_ref["k5"].computed_result is None
    assert (
        conn.execute("SELECT COUNT(*) FROM claim_citations WHERE claim_id = ?", (by_ref["k3"].id,)).fetchone()[0] == 2
    )
    assert conn.execute("SELECT COUNT(*) FROM app_events WHERE event_type = 'claims.drafted'").fetchone()[0] == 1


def test_carried_verdict(conn: sqlite3.Connection, ctx: RequestContext, question: dict[str, str]) -> None:
    c1 = question["c1"]
    [first] = _store(conn, ctx, 1, [_claim("k1", "Price is 29.00.", citationIds=[c1])])
    assert first.carried is None
    with transaction(conn):
        conn.execute(
            "INSERT INTO verifications VALUES ('v_1', (SELECT workspace_id FROM questions), 'q_1', 'r_1', 't_1', 1, ?)",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO verdicts (verification_id, claim_id, verdict, reason) VALUES ('v_1', ?, 'supported', 'Stated.')",
            (first.id,),
        )
    same, changed = _store(conn, ctx, 2, [
        _claim("k1", "Price is 29.00.", citationIds=[c1]), _claim("k2", "Price is 29.00 each.", citationIds=[c1]),
    ])  # fmt: skip
    assert same.content_sha256 == first.content_sha256 and same.id != first.id
    assert same.carried is not None and (same.carried.verdict, same.carried.reason) == ("supported", "Stated.")
    assert changed.carried is None


def test_pass_rule() -> None:
    assert passes(["supported", "supported"])
    for bad in ("partly_supported", "unsupported", "mechanical_fail"):
        assert not passes(["supported", bad])


DEMO_CLAIMS = {
    "k1": "Andes Green Coffee raises its price by 8% from 1 January 2027.",
    "k2": "In Q3 2026 the average price was $29.00 per kg, cost of goods was $13.05 per kg, of which green coffee was $7.60, and gross margin was 55.0%.",
    "k3": "The board holds retail prices until the March 2027 meeting and keeps the gross margin target at 55%.",
    "k4b": "The pricing policy requires a price review when cost of goods moves by more than 5%.",
    "k5": "With green coffee up 8%, cost of goods becomes $13.66 per kg and gross margin at $29.00 falls to 52.9%.",
    "k6": "Keeping a 55% margin needs a price of about $30.35 per kg, a rise of about 4.7%.",
    "k7": "Cost of goods rises by about 4.7%, which is below the 5% review trigger.",
    "k8": "The price hold and the 55% margin target cannot both be kept.",
}
DEMO_CITATIONS = {
    "k1": ["c1"], "k2": ["c2"], "k3": ["c3"], "k4b": ["c4"], "k5": ["c1", "c2"], "k6": ["c1", "c2", "c3"],
    "k7": ["c1", "c2", "c4"], "k8": ["c3", "c1", "c2"],
}  # fmt: skip
DEMO_SEGMENTS = [
    Segment(text="Not without changing something."),
    Segment(text="From 1 January 2027, Andes Green Coffee raises its price by 8%.", claim_ids=["k1"]),
    Segment(text="At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9%.", claim_ids=["k2", "k5"]),
    Segment(text="That is below the board's 55% target.", claim_ids=["k3"]),
    Segment(
        text="The board also decided to hold retail prices until March 2027.", claim_ids=["k3"], new_paragraph=True
    ),
    Segment(text="The pricing policy requires a review only when cost of goods moves more than 5%.", claim_ids=["k4b"]),
    Segment(text="This change is about 4.7%, so the policy does not force one.", claim_ids=["k7"]),
    Segment(
        text="To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7%.", claim_ids=["k6"]
    ),
    Segment(text="The price hold and the margin target cannot both be kept.", claim_ids=["k8"]),
    Segment(text="This needs a board decision."),
]
DEMO_TEXT = (
    "Not without changing something. From 1 January 2027, Andes Green Coffee raises its price by 8% [1]. "
    "At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9% [1][2]. "
    "That is below the board's 55% target [3].\n\n"
    "The board also decided to hold retail prices until March 2027 [3]. "
    "The pricing policy requires a review only when cost of goods moves more than 5% [4]. "
    "This change is about 4.7%, so the policy does not force one [1][2][4]. "
    "To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7% [1][2][3]. "
    "The price hold and the margin target cannot both be kept [1][2][3]. This needs a board decision."
)


def test_assemble_answer() -> None:
    assert validate_segments(DEMO_SEGMENTS, DEMO_CLAIMS, "full") == []
    text, order = assemble_answer(DEMO_SEGMENTS, DEMO_CITATIONS)
    assert text == DEMO_TEXT
    assert order == ["c1", "c2", "c3", "c4"]
    assert (
        assemble_answer([Segment(text="No punctuation", claim_ids=["k1"])], DEMO_CITATIONS)[0] == "No punctuation [1]"
    )


def test_answer_guards() -> None:
    verified = {"k1": "Rent rises by 8% in 2027.", "k2": "There are 5,150 kg."}
    assert (
        "may not contain digits"
        in validate_segments([Segment(text="In 2027 things change.")], verified, "nothing_found")[0]
    )
    assert "writes 9" in validate_segments([Segment(text="Rent rises by 9%.", claim_ids=["k1"])], verified, "full")[0]
    assert validate_segments([Segment(text="We sold 5150 kg.", claim_ids=["k2"])], verified, "full") == []
    assert "not a verified claim" in validate_segments([Segment(text="Rent.", claim_ids=["k9"])], verified, "full")[0]
    assert "at least one segment" in validate_segments([Segment(text="Nothing here.")], verified, "partial")[0]
    assert validate_segments([Segment(text="No files yet.")], {}, "no_files") == []


def test_fallback_answer() -> None:
    text, order = fallback_answer(
        [ClaimRef(claim_id="k1", text=DEMO_CLAIMS["k1"]), ClaimRef(claim_id="k5", text=DEMO_CLAIMS["k5"])],
        DEMO_CITATIONS,
    )
    assert text == (
        "Andes Green Coffee raises its price by 8% from 1 January 2027 [1]. "
        "With green coffee up 8%, cost of goods becomes $13.66 per kg and gross margin at $29.00 falls to 52.9% [1][2]."
    )
    assert order == ["c1", "c2"]
