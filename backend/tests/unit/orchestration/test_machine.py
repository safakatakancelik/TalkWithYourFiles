import ast
from dataclasses import replace
from pathlib import Path

import pytest

from twyf.orchestration import machine
from twyf.orchestration.machine import (
    FINAL_STATES,
    AnswerWritten,
    Assign,
    AssignDone,
    Assignment,
    Call,
    Cancel,
    CancelTurns,
    ClaimsDrafted,
    Complete,
    EmitAnswer,
    EmitBroadcast,
    EmitCancelled,
    EmitContext,
    EmitError,
    EmitRehuddle,
    EmitVerdict,
    EmitVerify,
    FailedClaim,
    Fatal,
    InvalidTransition,
    Join,
    Leave,
    PlanDone,
    QEvent,
    QState,
    ReviewDone,
    RunAssign,
    RunDraftClaims,
    RunPlan,
    RunReview,
    RunSoloAssign,
    RunVerify,
    RunVolunteers,
    RunWork,
    RunWriteAnswer,
    Say,
    Start,
    StartRound,
    Verified,
    Volunteer,
    VolunteersDone,
    WorkDone,
    transition,
)

CALL = Call("a_2", ("f_1",), "named")
VOL = Volunteer("a_1", "I read leases", ("f_1",))
A1 = Assignment("a_1", ("f_1",), "end date")
A2 = Assignment("a_2", ("f_1",), "rent", how="called")
FAIL = FailedClaim("k_1", "Rent rises 10%.", "unsupported", "Says 8%.")
IN = frozenset({"a_1"})

ROWS = [
    ("no ready files", QState("received"), Start(0), QState("writing"), [RunWriteAnswer("no_files")]),
    ("start", QState("received"), Start(2), QState("planning", round_no=1), [StartRound(1, "initial"), RunPlan()]),
    ("start, one translator", QState("received"), Start(2, solo=True), QState("assigning", round_no=1, solo=True),
     [StartRound(1, "initial"), RunSoloAssign()]),
    ("plan, someone to ask", QState("planning", 1), PlanDone(("a_1",), (CALL,)), QState("broadcasting", 1),
     [EmitBroadcast(("a_1",)), RunVolunteers(("a_1",))]),
    ("plan, nobody to ask", QState("planning", 1), PlanDone((), (CALL,)), QState("assigning", 1), [RunAssign((), (CALL,))]),
    ("volunteers", QState("broadcasting", 1), VolunteersDone((VOL,), (CALL,)), QState("assigning", 1),
     [RunAssign((VOL,), (CALL,))]),
    ("assign", QState("assigning", 1), AssignDone((A1, A2)), QState("working", 1, members=frozenset({"a_1", "a_2"})),
     [Join((("a_1", "volunteered"), ("a_2", "called"))), Assign((A1, A2)), RunWork((A1, A2))]),
    ("assign nothing", QState("assigning", 1), AssignDone(()), QState("drafting", 1), [RunDraftClaims()]),
    ("work done", QState("working", 1, members=frozenset({"a_1", "a_2"})), WorkDone(frozenset({"a_2"})),
     QState("reviewing", 1, members=IN), [RunReview(())]),
    ("review continue", QState("reviewing", 1, members=IN), ReviewDone("continue", (A1, A2)),
     QState("working", 1, steps=1, members=frozenset({"a_1", "a_2"})),
     [Say(), Join((("a_2", "called"),)), Assign((A2,)), RunWork((A1, A2))]),
    ("review settle", QState("reviewing", 1, members=IN), ReviewDone("settle"), QState("drafting", 1, members=IN),
     [Say(), RunDraftClaims()]),
    ("review continue, no followups", QState("reviewing", 1, members=IN), ReviewDone("continue"),
     QState("drafting", 1, members=IN), [Say(), RunDraftClaims()]),
    ("no claims", QState("drafting", 1, members=IN), ClaimsDrafted(0), QState("writing", 1),
     [Leave(("a_1",), "settled"), RunWriteAnswer("nothing_found")]),
    ("claims", QState("drafting", 1, members=IN), ClaimsDrafted(3), QState("verifying", 1, members=IN),
     [EmitVerify(), RunVerify()]),
    ("verified", QState("verifying", 1, members=IN), Verified(True), QState("writing", 1),
     [EmitVerdict(), Leave(("a_1",), "settled"), RunWriteAnswer("full")]),
    ("verification failed, rounds left", QState("verifying", 1, steps=4, members=IN), Verified(False, (FAIL,)),
     QState("reviewing", 2, steps=0, members=IN),
     [EmitVerdict(), EmitRehuddle(2, (FAIL,)), StartRound(2, "verification_failed"), RunReview((FAIL,))]),
    ("verification failed, last round", QState("verifying", 3, members=IN), Verified(False, (FAIL,)),
     QState("writing", 3, partial=True), [EmitVerdict(), Leave(("a_1",), "settled"), RunWriteAnswer("partial")]),
    ("answer", QState("writing", 1), AnswerWritten(), QState("answered", 1), [EmitContext(), EmitAnswer(), Complete()]),
    ("partial answer", QState("writing", 3, partial=True), AnswerWritten(), QState("answered_partial", 3, partial=True),
     [EmitContext(), EmitAnswer(), Complete()]),
    ("cancel", QState("working", 1, members=IN), Cancel(), QState("cancelled", 1),
     [CancelTurns(), Leave(("a_1",), "cancelled"), EmitCancelled()]),
    ("fatal", QState("verifying", 1, members=IN), Fatal("verifier_unavailable", "no verifier"), QState("failed", 1),
     [CancelTurns(), Leave(("a_1",), "failed"), EmitError("verifier_unavailable", "no verifier")]),
]  # fmt: skip


@pytest.mark.parametrize(("state", "event", "expected", "commands"), [r[1:] for r in ROWS], ids=[r[0] for r in ROWS])
def test_machine_every_row(state: QState, event: QEvent, expected: QState, commands: list[object]) -> None:
    assert transition(state, event) == (expected, commands)


NON_FINAL = [
    "received",
    "planning",
    "broadcasting",
    "assigning",
    "working",
    "reviewing",
    "drafting",
    "verifying",
    "writing",
]
EVENTS: list[QEvent] = [
    Start(1), PlanDone(()), VolunteersDone(()), AssignDone(()), WorkDone(), ReviewDone("settle"), ClaimsDrafted(1),
    Verified(True), AnswerWritten(),
]  # fmt: skip
VALID = {
    ("received", "Start"), ("planning", "PlanDone"), ("broadcasting", "VolunteersDone"), ("assigning", "AssignDone"),
    ("working", "WorkDone"), ("reviewing", "ReviewDone"), ("drafting", "ClaimsDrafted"), ("verifying", "Verified"),
    ("writing", "AnswerWritten"),
}  # fmt: skip


def test_machine_invalid_pairs() -> None:
    for name in NON_FINAL:
        for event in EVENTS:
            if (name, type(event).__name__) in VALID:
                transition(QState(name, 1), event)
            else:
                with pytest.raises(InvalidTransition):
                    transition(QState(name, 1), event)
    for name in FINAL_STATES:
        for event in [*EVENTS, Cancel(), Fatal("x", "y")]:
            assert transition(QState(name), event) == (QState(name), [])


def test_machine_round_limit() -> None:
    for max_rounds, failures in ((3, 3), (1, 1)):
        state, _ = transition(QState("received", max_rounds=max_rounds), Start(1))
        for _ in range(failures):
            state = replace(state, name="verifying")
            state, commands = transition(state, Verified(False, (FAIL,)))
        assert state.name == "writing" and state.partial is True
        assert commands[-1] == RunWriteAnswer("partial")
        assert state.round_no == max_rounds


def test_machine_step_limit() -> None:
    state = QState("reviewing", 1, max_steps=2, members=IN)
    for _ in range(2):
        state, commands = transition(state, ReviewDone("continue", (A1,)))
        assert state.name == "working" and isinstance(commands[-1], RunWork)
        state, _ = transition(state, WorkDone())
    assert state.steps == 2
    state, commands = transition(state, ReviewDone("continue", (A1,)))
    assert state.name == "drafting" and commands == [Say(), RunDraftClaims()]


def test_machine_is_pure() -> None:
    tree = ast.parse(Path(machine.__file__).read_text())
    imported = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in imported if m.startswith("twyf")]
    assert set(imported) <= {"dataclasses"}


def test_machine_solo_skips_review_after_work() -> None:
    solo = QState("working", 1, members=IN, solo=True)
    assert transition(solo, WorkDone()) == (QState("drafting", 1, members=IN, solo=True), [RunDraftClaims()])
    huddle = QState("working", 1, members=IN)
    assert transition(huddle, WorkDone()) == (QState("reviewing", 1, members=IN), [RunReview(())])
