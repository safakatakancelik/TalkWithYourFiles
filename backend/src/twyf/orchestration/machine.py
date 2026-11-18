"""The orchestrator's state machine (04-agents.md section 5). A pure function: no I/O, no imports from twyf."""

from dataclasses import dataclass, replace

FINAL_STATES: frozenset[str] = frozenset({"answered", "answered_partial", "failed", "cancelled", "interrupted"})


class InvalidTransition(Exception):
    pass


@dataclass(frozen=True)
class QState:
    name: str  # a code from question_states
    round_no: int = 0  # verification rounds started
    steps: int = 0  # review turns taken in this round
    max_rounds: int = 3
    max_steps: int = 6
    members: frozenset[str] = frozenset()
    partial: bool = False
    solo: bool = False  # one translator in the workspace: no plan, volunteer, assign or review of finished work


# What the commands carry


@dataclass(frozen=True)
class Call:
    agent_id: str
    file_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Volunteer:
    agent_id: str
    reason: str
    file_ids: tuple[str, ...]


@dataclass(frozen=True)
class Assignment:
    agent_id: str
    file_ids: tuple[str, ...]
    focus: str
    how: str = "volunteered"  # 'volunteered' | 'called'


@dataclass(frozen=True)
class FailedClaim:
    claim_id: str
    text: str
    verdict: str
    reason: str


# Events


@dataclass(frozen=True)
class Start:
    ready_files: int
    solo: bool = False


@dataclass(frozen=True)
class PlanDone:
    to: tuple[str, ...]
    calls: tuple[Call, ...] = ()


@dataclass(frozen=True)
class VolunteersDone:
    volunteers: tuple[Volunteer, ...]
    calls: tuple[Call, ...] = ()  # the plan's direct calls, carried for RunAssign


@dataclass(frozen=True)
class AssignDone:
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class WorkDone:
    left: frozenset[str] = frozenset()  # agents that failed and already left


@dataclass(frozen=True)
class ReviewDone:
    decision: str  # 'continue' | 'settle'
    followups: tuple[Assignment, ...] = ()


@dataclass(frozen=True)
class ClaimsDrafted:
    n: int


@dataclass(frozen=True)
class Verified:
    passed: bool
    failed: tuple[FailedClaim, ...] = ()


@dataclass(frozen=True)
class AnswerWritten:
    pass


@dataclass(frozen=True)
class Cancel:
    pass


@dataclass(frozen=True)
class Fatal:
    code: str
    message: str


type QEvent = (
    Start | PlanDone | VolunteersDone | AssignDone | WorkDone | ReviewDone | ClaimsDrafted | Verified | AnswerWritten
    | Cancel | Fatal
)  # fmt: skip


# Commands


@dataclass(frozen=True)
class StartRound:
    round_no: int
    reason: str


@dataclass(frozen=True)
class RunPlan:
    pass


@dataclass(frozen=True)
class RunSoloAssign:
    """Give every ready file to the workspace's only translator, without asking the orchestrator."""


@dataclass(frozen=True)
class EmitBroadcast:
    to: tuple[str, ...]


@dataclass(frozen=True)
class RunVolunteers:
    to: tuple[str, ...]


@dataclass(frozen=True)
class RunAssign:
    volunteers: tuple[Volunteer, ...]
    calls: tuple[Call, ...]


@dataclass(frozen=True)
class Join:
    agents: tuple[tuple[str, str], ...]  # (agent_id, how)


@dataclass(frozen=True)
class Assign:
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class RunWork:
    assignments: tuple[Assignment, ...]


@dataclass(frozen=True)
class Say:
    agent: str = "orchestrator"


@dataclass(frozen=True)
class RunReview:
    failed: tuple[FailedClaim, ...] = ()


@dataclass(frozen=True)
class RunDraftClaims:
    pass


@dataclass(frozen=True)
class EmitVerify:
    pass


@dataclass(frozen=True)
class RunVerify:
    pass


@dataclass(frozen=True)
class EmitVerdict:
    pass


@dataclass(frozen=True)
class EmitRehuddle:
    round_no: int  # the round that now starts
    failed: tuple[FailedClaim, ...] = ()


@dataclass(frozen=True)
class Leave:
    agent_ids: tuple[str, ...]
    reason: str  # 'settled' | 'failed' | 'cancelled'


@dataclass(frozen=True)
class RunWriteAnswer:
    mode: str  # 'full' | 'partial' | 'nothing_found' | 'no_files'


@dataclass(frozen=True)
class EmitContext:
    pass


@dataclass(frozen=True)
class EmitAnswer:
    pass


@dataclass(frozen=True)
class Complete:
    pass


@dataclass(frozen=True)
class CancelTurns:
    pass


@dataclass(frozen=True)
class EmitCancelled:
    pass


@dataclass(frozen=True)
class EmitError:
    code: str
    message: str


type Command = (
    StartRound | RunPlan | RunSoloAssign | EmitBroadcast | RunVolunteers | RunAssign | Join | Assign | RunWork | Say | RunReview
    | RunDraftClaims | EmitVerify | RunVerify | EmitVerdict | EmitRehuddle | Leave | RunWriteAnswer | EmitContext
    | EmitAnswer | Complete | CancelTurns | EmitCancelled | EmitError
)  # fmt: skip


def _members(state: QState) -> tuple[str, ...]:
    return tuple(sorted(state.members))


def _joins(state: QState, assignments: tuple[Assignment, ...]) -> tuple[tuple[str, str], ...]:
    """Each agent not yet in the huddle, once, in assignment order."""
    seen: dict[str, str] = {}
    for a in assignments:
        if a.agent_id not in state.members and a.agent_id not in seen:
            seen[a.agent_id] = a.how
    return tuple(seen.items())


def _leave_all(state: QState, name: str, reason: str, *, partial: bool | None = None) -> QState:
    return replace(state, name=name, members=frozenset(), partial=state.partial if partial is None else partial)


def transition(state: QState, event: QEvent) -> tuple[QState, list[Command]]:
    """The next state and the commands to execute, in order. Raises InvalidTransition for any other pair."""
    if state.name in FINAL_STATES:
        return state, []
    if isinstance(event, Cancel):
        return _leave_all(state, "cancelled", "cancelled"), [
            CancelTurns(),
            Leave(_members(state), "cancelled"),
            EmitCancelled(),
        ]
    if isinstance(event, Fatal):
        commands: list[Command] = [
            CancelTurns(),
            Leave(_members(state), "failed"),
            EmitError(event.code, event.message),
        ]
        return _leave_all(state, "failed", "failed"), commands
    match state.name, event:
        case "received", Start(ready_files=0):
            return replace(state, name="writing"), [RunWriteAnswer("no_files")]
        case "received", Start(solo=True):
            return replace(state, name="assigning", round_no=1, steps=0, solo=True), [
                StartRound(1, "initial"),
                RunSoloAssign(),
            ]
        case "received", Start():
            return replace(state, name="planning", round_no=1, steps=0), [StartRound(1, "initial"), RunPlan()]
        case "planning", PlanDone(to=to, calls=calls) if to:
            return replace(state, name="broadcasting"), [EmitBroadcast(to), RunVolunteers(to)]
        case "planning", PlanDone(calls=calls):
            return replace(state, name="assigning"), [RunAssign((), calls)]
        case "broadcasting", VolunteersDone(volunteers=volunteers, calls=calls):
            return replace(state, name="assigning"), [RunAssign(volunteers, calls)]
        case "assigning", AssignDone(assignments=assignments) if assignments:
            joined = _joins(state, assignments)
            members = state.members | {a.agent_id for a in assignments}
            next_state = replace(state, name="working", members=members)
            return next_state, [Join(joined), Assign(assignments), RunWork(assignments)]
        case "assigning", AssignDone():
            return replace(state, name="drafting"), [RunDraftClaims()]
        case "working", WorkDone(left=left) if state.solo:
            return replace(state, name="drafting", members=state.members - left), [RunDraftClaims()]
        case "working", WorkDone(left=left):
            return replace(state, name="reviewing", members=state.members - left), [RunReview(())]
        case "reviewing", ReviewDone(decision="continue", followups=followups) if (
            state.steps < state.max_steps and followups
        ):
            joined = _joins(state, followups)
            new = tuple(a for a in followups if a.agent_id in dict(joined))
            members = state.members | {a.agent_id for a in followups}
            next_state = replace(state, name="working", steps=state.steps + 1, members=members)
            return next_state, [Say(), Join(joined), Assign(new), RunWork(followups)]
        case "reviewing", ReviewDone():
            return replace(state, name="drafting"), [Say(), RunDraftClaims()]
        case "drafting", ClaimsDrafted(n=0):
            return _leave_all(state, "writing", "settled"), [
                Leave(_members(state), "settled"),
                RunWriteAnswer("nothing_found"),
            ]
        case "drafting", ClaimsDrafted():
            return replace(state, name="verifying"), [EmitVerify(), RunVerify()]
        case "verifying", Verified(passed=True):
            commands = [EmitVerdict(), Leave(_members(state), "settled"), RunWriteAnswer("full")]
            return _leave_all(state, "writing", "settled"), commands
        case "verifying", Verified(failed=failed) if state.round_no < state.max_rounds:
            next_round = state.round_no + 1
            commands = [
                EmitVerdict(), EmitRehuddle(next_round, failed), StartRound(next_round, "verification_failed"),
                RunReview(failed),
            ]  # fmt: skip
            return replace(state, name="reviewing", round_no=next_round, steps=0), commands
        case "verifying", Verified():
            commands = [EmitVerdict(), Leave(_members(state), "settled"), RunWriteAnswer("partial")]
            return _leave_all(state, "writing", "settled", partial=True), commands
        case "writing", AnswerWritten():
            name = "answered_partial" if state.partial else "answered"
            return replace(state, name=name), [EmitContext(), EmitAnswer(), Complete()]
        case _:
            raise InvalidTransition(f"{type(event).__name__} in state {state.name}")
