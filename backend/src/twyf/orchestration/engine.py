"""Runs a question: feeds the state machine's events and executes its commands (04-agents.md sections 4 to 10)."""

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from twyf.citations.check import check
from twyf.citations.locate import create_citation, try_quote
from twyf.config import Settings
from twyf.contextmap.service import add_mentions
from twyf.contract.events import (
    AgentEvent,
    AnswerEvent,
    AssignEvent,
    BroadcastEvent,
    CancelledEvent,
    ContextEvent,
    ErrorEvent,
    JoinEvent,
    LeaveEvent,
    ReadingEvent,
    RehuddleEvent,
    SayEvent,
    StatusEvent,
    VerdictEvent,
    VerifyEvent,
)
from twyf.contract.models import ORCHESTRATOR, Citation, Claim, MapLink, MapNode, Unverified, Verdict
from twyf.contract.turns import (
    AssignInput,
    AssignOutput,
    ClaimIn,
    ClaimRef,
    DirectCall,
    DraftClaimsInput,
    DraftClaimsOutput,
    EarlierClaim,
    Feedback,
    Line,
    PassageIn,
    PlanInput,
    PlanOutput,
    Quote,
    ReviewInput,
    ReviewOutput,
    VerifyInput,
    VerifyOutput,
    VolunteerInput,
    VolunteerOutput,
    WorkInput,
    WorkOutput,
    WriteAnswerInput,
    WriteAnswerOutput,
)
from twyf.contract.turns import (
    FailedClaim as FailedClaimIn,
)
from twyf.contract.turns import (
    Volunteer as VolunteerIn,
)
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import citations as citations_repo
from twyf.db.repos import files as files_repo
from twyf.db.repos import huddle
from twyf.db.repos import questions as questions_repo
from twyf.db.repos import turns as turns_repo
from twyf.db.repos import verifications as verifications_repo
from twyf.db.repos.claims import ClaimRow
from twyf.db.repos.verifications import VerdictRow
from twyf.files.integrity import verify as verify_file
from twyf.files.integrity import verify_workspace
from twyf.ids import new_id
from twyf.orchestration import claims as claim_rules
from twyf.orchestration import inputs, validators
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
    Command,
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
from twyf.recording.broker import EventBroker
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval.hybrid import Passage, Retriever
from twyf.retrieval.weights import notes_for_turn
from twyf.runtime.runner import TurnFailed, TurnRunner
from twyf.services.notes import create_agent_note
from twyf.services.sessions import add_message

log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]

NO_FILES = "There are no files in this workspace yet."
NOTHING_FOUND = "The files do not answer this question."
named = inputs.named


@dataclass
class Q:
    """What the engine keeps while one question runs."""

    question_id: str
    workspace_id: str
    session_id: str
    text: str
    ctx: RequestContext  # the asker's context, caused by question.asked
    orchestrator: str
    verifier: str
    chat: str
    translators: dict[str, str] = field(default_factory=dict[str, str])  # id -> name
    round_id: str | None = None
    round_no: int = 0
    plan: PlanOutput | None = None
    numbers: dict[str, int] = field(default_factory=dict[str, int])  # citation id -> n in this question
    transcript: list[Line] = field(default_factory=list[Line])
    files_of: dict[str, list[str]] = field(default_factory=dict[str, list[str]])  # agent -> assigned files
    review: ReviewOutput | None = None
    round_claims: list[ClaimRow] = field(default_factory=list[ClaimRow])
    verdicts: dict[str, VerdictRow] = field(default_factory=dict[str, VerdictRow])  # claim id -> verdict, this round
    earlier: list[EarlierClaim] = field(default_factory=list[EarlierClaim])
    answer_text: str = ""
    answer_citations: list[str] = field(default_factory=list[str])
    answer_claims: list[str] = field(default_factory=list[str])
    unverified: list[Unverified] = field(default_factory=list[Unverified])
    nodes: list[MapNode] = field(default_factory=list[MapNode])
    links: list[MapLink] = field(default_factory=list[MapLink])
    cancel_ctx: RequestContext | None = None

    def number(self, citation_id: str) -> int:
        if citation_id not in self.numbers:
            self.numbers[citation_id] = len(self.numbers) + 1
        return self.numbers[citation_id]


class Engine:
    def __init__(
        self,
        settings: Settings,
        conn_factory: ConnFactory,
        runner: TurnRunner,
        retriever: Retriever,
        broker: EventBroker,
    ) -> None:
        self.settings = settings
        self.conn_factory = conn_factory
        self.runner = runner
        self.retriever = retriever
        self.broker = broker
        self.running: dict[str, Q] = {}

    # --- plumbing -------------------------------------------------------------------------------------------

    def _with_conn[T](self, fn: Callable[[sqlite3.Connection], T], write: bool = True) -> T:
        conn = self.conn_factory()
        try:
            if not write:
                return fn(conn)
            with transaction(conn):
                return fn(conn)
        finally:
            conn.close()

    async def _db[T](self, fn: Callable[[sqlite3.Connection], T], write: bool = True) -> T:
        return await asyncio.to_thread(self._with_conn, fn, write)

    def _emit(
        self, conn: sqlite3.Connection, q: Q, actor: str, event_type: str, wire: AgentEvent | None = None, *,
        source: str = "internal", **kwargs: Any,
    ) -> int:  # fmt: skip
        ctx = q.ctx.as_actor(actor, source)
        return record(
            conn, ctx, event_type, workspace_id=q.workspace_id, session_id=q.session_id, question_id=q.question_id,
            round_id=q.round_id, wire=wire, **kwargs,
        )  # fmt: skip

    def _agent_ctx(self, q: Q, agent_id: str) -> RequestContext:
        return q.ctx.as_actor(agent_id)

    def _wire_agent(self, q: Q, agent_id: str) -> str:
        if agent_id == q.orchestrator:
            return ORCHESTRATOR
        return agent_id

    async def _status(self, q: Q, text: str) -> None:
        await self._db(lambda c: self._emit(c, q, "system", "question.status", StatusEvent(text=text)))

    def _citation(self, conn: sqlite3.Connection, q: Q, citation_id: str) -> Citation:
        return citations_repo.to_wire(conn, citation_id, q.number(citation_id))

    # --- the loop --------------------------------------------------------------------------------------------

    def cancel_context(self, question_id: str, ctx: RequestContext) -> None:
        """Who cancelled, so question.cancelled names them."""
        if question_id in self.running:
            self.running[question_id].cancel_ctx = ctx

    async def run(self, ctx: RequestContext, question_id: str) -> None:
        q = await self._db(lambda c: self._load(c, ctx, question_id), write=False)
        self.running[question_id] = q
        state = QState(
            "received", max_rounds=self.settings.max_verify_rounds, max_steps=self.settings.max_discussion_steps
        )
        try:
            event: QEvent | None = await self._start(q)
            while event is not None and state.name not in FINAL_STATES:
                state, event = await self._step(q, state, event)
        except asyncio.CancelledError:
            await asyncio.shield(self._step(q, state, Cancel()))
            raise
        finally:
            self.running.pop(question_id, None)
            self.broker.close(question_id)

    async def _step(self, q: Q, state: QState, event: QEvent) -> tuple[QState, QEvent | None]:
        new_state, commands = transition(state, event)
        if new_state.name != state.name:
            await self._db(lambda c: self._changed(c, q, state.name, new_state.name))
        next_event: QEvent | None = None
        for command in commands:
            try:
                produced = await self._execute(q, new_state, command)
            except TurnFailed as failed:
                produced = self._fatal_for(q, failed)
            if produced is not None:
                if isinstance(produced, Fatal) and new_state.name not in FINAL_STATES:
                    return await self._step(q, new_state, produced)
                next_event = produced
        return new_state, next_event

    def _fatal_for(self, q: Q, failed: TurnFailed) -> Fatal:
        code = {"verify": "verifier_unavailable"}.get(failed.turn_type, f"{failed.turn_type}_failed")
        return Fatal(code, f"The {failed.turn_type} turn could not be completed: {failed.reason}")

    def _changed(self, conn: sqlite3.Connection, q: Q, old: str, new: str) -> None:
        if new not in FINAL_STATES:
            questions_repo.set_state(conn, q.question_id, new)
        self._emit(conn, q, "system", "question.state_changed", payload={"from": old, "to": new})

    def _load(self, conn: sqlite3.Connection, ctx: RequestContext, question_id: str) -> Q:
        row = questions_repo.by_id(conn, question_id)
        assert row is not None
        text = conn.execute(
            "SELECT text FROM messages WHERE question_id = ? AND role = 'user' ORDER BY created_at LIMIT 1",
            (question_id,),
        ).fetchone()[0]
        ws = row["workspace_id"]
        asked = conn.execute(
            "SELECT id FROM app_events WHERE question_id = ? AND event_type = 'question.asked'", (question_id,)
        ).fetchone()
        q = Q(
            question_id=question_id, workspace_id=ws, session_id=row["session_id"], text=text,
            ctx=ctx.caused_by(asked[0]) if asked is not None else ctx,
            orchestrator=agents_repo.builtin(conn, ws, "orchestrator").id,
            verifier=agents_repo.builtin(conn, ws, "verifier").id, chat=agents_repo.builtin(conn, ws, "chat").id,
        )  # fmt: skip
        q.translators = {a.id: a.name for a in agents_repo.list(conn, ws, "translator")}
        return q

    async def _start(self, q: Q) -> Start:
        def check_files(conn: sqlite3.Connection) -> tuple[int, list[str]]:
            bad = dict(verify_workspace(conn, q.ctx.as_actor("system"), q.workspace_id))
            named_files, _ = inputs.named(conn, q.workspace_id, q.text)
            names = [files_repo.get(conn, q.workspace_id, f) for f in named_files if f in bad]
            return len(inputs.usable_ready_files(conn, q.workspace_id)), [n["name"] for n in names if n is not None]

        ready, missing = await self._db(check_files, write=False)
        for name in missing:
            await self._status(q, f"{name} is no longer available and was left out.")
        return Start(ready)

    async def _execute(self, q: Q, state: QState, command: Command) -> QEvent | None:
        match command:
            case StartRound(round_no=n, reason=reason):
                await self._db(lambda c: self._start_round(c, q, n, reason))
            case RunPlan():
                return await self._plan(q)
            case EmitBroadcast(to=to):
                plan = q.plan
                assert plan is not None
                await self._db(lambda c: self._emit(c, q, q.orchestrator, "huddle.broadcast",
                                                    BroadcastEvent(text=plan.broadcast_text, to=list(to))))  # fmt: skip
            case RunVolunteers(to=to):
                return await self._volunteers(q, to)
            case RunAssign(volunteers=volunteers, calls=calls):
                return await self._assign_turn(q, volunteers, calls)
            case Join(agents=agents):
                await self._db(lambda c: self._join(c, q, agents))
            case Assign(assignments=assignments):
                await self._db(lambda c: self._assign(c, q, assignments))
            case RunWork(assignments=assignments):
                return await self._work_all(q, assignments)
            case Say():
                review = q.review
                if review is not None and review.say:
                    await self._db(lambda c: self._say(c, q, q.orchestrator, review.say, [], None))
            case RunReview(failed=failed):
                return await self._review(q, state, failed)
            case RunDraftClaims():
                return await self._draft(q)
            case EmitVerify():
                await self._db(lambda c: self._emit_verify(c, q))
            case RunVerify():
                return await self._verify(q)
            case EmitVerdict():
                await self._db(lambda c: self._emit_verdict(c, q))
            case EmitRehuddle(round_no=n, failed=failed):
                await self._db(lambda c: self._rehuddle(c, q, n, failed))
            case Leave(agent_ids=agent_ids, reason=reason):
                if agent_ids:
                    await self._db(lambda c: self._leave(c, q, list(agent_ids), reason))
            case RunWriteAnswer(mode=mode):
                return await self._write(q, mode)
            case EmitContext():
                if q.nodes or q.links:
                    await self._db(lambda c: self._emit(c, q, q.orchestrator, "context.extended",
                                                        ContextEvent(nodes=q.nodes, links=q.links)))  # fmt: skip
            case EmitAnswer():
                await self._db(lambda c: self._answer(c, q))
            case Complete():
                await self._db(lambda c: self._complete(c, q, state))
            case CancelTurns():
                await self._cancel_turns(q)
            case EmitCancelled():
                await self._db(lambda c: self._cancelled(c, q))
            case EmitError(code=code, message=message):
                await self._db(lambda c: self._error(c, q, code, message))
        return None

    # --- rounds, joins, assignments --------------------------------------------------------------------------

    def _start_round(self, conn: sqlite3.Connection, q: Q, n: int, reason: str) -> None:
        q.round_id, q.round_no = new_id("r"), n
        huddle.start_round(conn, round_id=q.round_id, workspace_id=q.workspace_id, question_id=q.question_id,
                           round_no=n, reason=reason)  # fmt: skip
        questions_repo.set_rounds(conn, q.question_id, n)
        q.round_claims, q.verdicts = [], {}
        self._emit(conn, q, "system", "huddle.round_started", payload={"round": n, "reason": reason})

    def _join(self, conn: sqlite3.Connection, q: Q, agents: tuple[tuple[str, str], ...]) -> None:
        for agent_id, how in agents:
            huddle.join(conn, workspace_id=q.workspace_id, question_id=q.question_id, agent_id=agent_id, how=how)
            self._emit(conn, q, agent_id, "huddle.member_joined", JoinEvent.model_validate({"agentId": agent_id, "how": how}),
                       entity_type="agent", entity_id=agent_id)  # fmt: skip

    def _assign(self, conn: sqlite3.Connection, q: Q, assignments: tuple[Assignment, ...]) -> None:
        for a in assignments:
            files = q.files_of.setdefault(a.agent_id, [])
            for file_id in a.file_ids:
                current = files_repo.get(conn, q.workspace_id, file_id)
                if current is None or file_id in files:
                    continue
                files.append(file_id)
                huddle.assign(conn, workspace_id=q.workspace_id, question_id=q.question_id, round_id=q.round_id,
                              agent_id=a.agent_id, file_id=file_id, file_version_id=current["file_version_id"],
                              purpose="huddle")  # fmt: skip
                self._emit(conn, q, q.orchestrator, "huddle.file_assigned", AssignEvent(agent_id=a.agent_id, file_id=file_id),
                           entity_type="file", entity_id=file_id, payload={"agent_id": a.agent_id})  # fmt: skip

    def _leave(self, conn: sqlite3.Connection, q: Q, agent_ids: list[str], reason: str) -> None:
        huddle.leave(conn, q.question_id, agent_ids, reason)
        self._emit(
            conn, q, q.orchestrator, "huddle.member_left", LeaveEvent(agent_ids=agent_ids), payload={"reason": reason}
        )

    # --- planning --------------------------------------------------------------------------------------------

    def _context(self, conn: sqlite3.Connection, q: Q) -> tuple[list[Any], list[Any], list[str], list[str]]:
        rows = inputs.usable_ready_files(conn, q.workspace_id)
        files = inputs.file_infos(conn, q.workspace_id, rows)
        agents = inputs.agent_infos(conn, q.workspace_id, {r["id"] for r in rows})
        named_files, named_agents = inputs.named(conn, q.workspace_id, q.text)
        usable = {r["id"] for r in rows}
        return files, agents, [f for f in named_files if f in usable], named_agents

    async def _plan(self, q: Q) -> PlanDone:
        files, agents, named_files, named_agents = await self._db(lambda c: self._context(c, q), write=False)
        history = await self._db(lambda c: inputs.history(c, q.session_id, q.question_id), write=False)
        plan_input = PlanInput(question=q.text, history=history, files=files, agents=agents,
                               named_file_ids=named_files, named_agent_ids=named_agents)  # fmt: skip
        translators = set(q.translators)

        def rules(out: PlanOutput) -> list[str]:
            return validators.unknown_ids(out, plan_input) + validators.plan(out, translators, named_agents)

        q.plan, _ = await self.runner.run(
            self._agent_ctx(q, q.orchestrator), agent_id=q.orchestrator, turn_type="plan", input=plan_input,
            output_model=PlanOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
        )  # fmt: skip
        calls = tuple(Call(c.agent_id, tuple(c.file_ids), c.reason) for c in q.plan.direct_calls)
        return PlanDone(tuple(dict.fromkeys(q.plan.broadcast_to)), calls)

    async def _volunteers(self, q: Q, to: tuple[str, ...]) -> VolunteersDone:
        files, _, _, _ = await self._db(lambda c: self._context(c, q), write=False)
        plan = q.plan
        assert plan is not None
        volunteer_input = VolunteerInput(question=q.text, broadcast_text=plan.broadcast_text, files=files)

        async def ask(agent_id: str) -> Volunteer | None:
            try:
                out, _ = await self.runner.run(
                    self._agent_ctx(q, agent_id), agent_id=agent_id, turn_type="volunteer", input=volunteer_input,
                    output_model=VolunteerOutput, validate=lambda o: validators.unknown_ids(o, volunteer_input),
                    question_id=q.question_id, round_id=q.round_id,
                )  # fmt: skip
            except TurnFailed:
                return None
            return Volunteer(agent_id, out.reason, tuple(out.file_ids)) if out.volunteer else None

        answers = await asyncio.gather(*(ask(a) for a in to))
        calls = tuple(Call(c.agent_id, tuple(c.file_ids), c.reason) for c in plan.direct_calls)
        return VolunteersDone(tuple(v for v in answers if v is not None), calls)

    async def _assign_turn(self, q: Q, volunteers: tuple[Volunteer, ...], calls: tuple[Call, ...]) -> AssignDone:
        files, agents, named_files, _ = await self._db(lambda c: self._context(c, q), write=False)
        assign_input = AssignInput(
            question=q.text, volunteers=[VolunteerIn(agent_id=v.agent_id, reason=v.reason, file_ids=list(v.file_ids)) for v in volunteers],
            direct_calls=[DirectCall(agent_id=c.agent_id, file_ids=list(c.file_ids), reason=c.reason) for c in calls],
            files=files, agents=agents, named_file_ids=named_files,
        )  # fmt: skip
        translators = set(q.translators)

        def rules(out: AssignOutput) -> list[str]:
            return validators.unknown_ids(out, assign_input) + validators.assign(out, translators, named_files)

        out, _ = await self.runner.run(
            self._agent_ctx(q, q.orchestrator), agent_id=q.orchestrator, turn_type="assign", input=assign_input,
            output_model=AssignOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
        )  # fmt: skip
        volunteered = {v.agent_id for v in volunteers}
        return AssignDone(tuple(
            Assignment(a.agent_id, tuple(dict.fromkeys(a.file_ids)), a.focus, "volunteered" if a.agent_id in volunteered else "called")
            for a in out.assignments if a.file_ids
        ))  # fmt: skip

    # --- work ------------------------------------------------------------------------------------------------

    async def _work_all(self, q: Q, assignments: tuple[Assignment, ...]) -> QEvent:
        feedback = [Feedback(claim_text=e.text, reason=e.reason) for e in q.earlier if e.verdict != "supported"]
        results = await asyncio.gather(*(self._work(q, a, feedback) for a in assignments))
        ran = [a.agent_id for a, r in zip(assignments, results, strict=True) if r is not None]
        failed = [a for a, r in zip(ran, [r for r in results if r is not None], strict=True) if r is False]
        if ran and len(failed) == len(ran):
            return Fatal("huddle_failed", "Every translator in the huddle failed.")
        return WorkDone(frozenset(failed))

    async def _work(self, q: Q, a: Assignment, feedback: list[Feedback]) -> bool | None:
        """True when the agent worked, False when its turn failed (it has left), None when it had no file."""

        def usable(conn: sqlite3.Connection) -> tuple[list[str], list[str]]:
            ok: list[str] = []
            gone: list[str] = []
            for file_id in a.file_ids or tuple(q.files_of.get(a.agent_id, [])):
                row = files_repo.get(conn, q.workspace_id, file_id)
                if row is not None and verify_file(conn, q.ctx.as_actor("system"), row["file_version_id"]) == "ok":
                    ok.append(file_id)
                elif row is not None:
                    gone.append(row["name"])
            return ok, gone

        file_ids, gone = await self._db(usable, write=False)
        for name in gone:
            await self._status(q, f"{name} is no longer available and was left out.")
        if not file_ids:
            return None
        agent_ctx = self._agent_ctx(q, a.agent_id)
        await self._db(lambda c: self._emit(c, q, a.agent_id, "huddle.reading", ReadingEvent(agent_id=a.agent_id)))
        query = f"{q.text} {a.focus}".strip()
        passages = await asyncio.to_thread(
            self.retriever.search, agent_ctx, workspace_id=q.workspace_id, query=query, file_ids=file_ids,
            k=self.settings.passages_per_turn,
        )  # fmt: skip
        notes = await self._db(
            lambda c: notes_for_turn(c, workspace_id=q.workspace_id, file_ids=file_ids, query=query), write=False
        )
        searches_left = self.settings.searches_per_turn
        try:
            while True:
                work_input = WorkInput(
                    question=q.text, focus=a.focus, passages=[self._passage_in(p) for p in passages], notes=notes,
                    transcript=list(q.transcript), feedback=feedback, searches_left=searches_left,
                )  # fmt: skip
                out, turn_id = await self.runner.run(
                    agent_ctx, agent_id=a.agent_id, turn_type="work", input=work_input, output_model=WorkOutput,
                    validate=self._work_rules(q, a.agent_id, work_input, searches_left), question_id=q.question_id,
                    round_id=q.round_id,
                )  # fmt: skip
                if not out.searches or searches_left <= 0:
                    break
                seen = {p.chunk_id for p in passages}
                for search in out.searches[:searches_left]:
                    targets = [search.file_id] if search.file_id in file_ids else file_ids
                    found = await asyncio.to_thread(
                        self.retriever.search, agent_ctx, workspace_id=q.workspace_id, query=search.query,
                        file_ids=targets, k=self.settings.passages_per_turn,
                    )  # fmt: skip
                    passages += [p for p in found if p.chunk_id not in seen]
                    seen |= {p.chunk_id for p in found}
                    searches_left -= 1
        except TurnFailed:
            await self._db(lambda c: self._leave(c, q, [a.agent_id], "failed"))
            return False
        by_passage = {p.passage_id: p.file_id for p in passages}
        await self._db(lambda c: self._store_work(c, q, a.agent_id, turn_id, out, by_passage))
        return True

    @staticmethod
    def _passage_in(p: Passage) -> PassageIn:
        return PassageIn(
            passage_id=p.passage_id, file_id=p.file_id, file_name=p.file_name, location=p.location, text=p.text
        )

    def _quote_check(
        self, conn: sqlite3.Connection, q: Q, agent_id: str, passages: dict[str, str]
    ) -> validators.QuoteCheck:
        def check_one(quote: Quote, own_file: str | None) -> str | None:
            if quote.citation_id is not None:
                row = citations_repo.get(conn, quote.citation_id)
                current = files_repo.get(conn, q.workspace_id, row.file_id) if row is not None else None
                if row is None or quote.citation_id not in q.numbers:
                    return f"citation {quote.citation_id} was not made in this question"
                if current is None or current["file_version_id"] != row.file_version_id:
                    return f"citation {quote.citation_id} is into an earlier version of its file and cannot be reused"
                if own_file is not None and row.file_id != own_file:
                    return f"citation {quote.citation_id} is not from the note's own file"
                return None
            if quote.passage_id is None or quote.quote is None:
                return "a quote needs passageId and quote, or citationId"
            if quote.passage_id not in passages:
                return f"passage {quote.passage_id} is not in the input"
            if own_file is not None and passages[quote.passage_id] != own_file:
                return f"quote {quote.quote!r} is not from the note's own file"
            reason = try_quote(conn, self._agent_ctx(q, agent_id), workspace_id=q.workspace_id,
                               passage_id=quote.passage_id, quote=quote.quote)  # fmt: skip
            return f"{reason}: {quote.quote!r} was not found in passage {quote.passage_id}" if reason else None

        return check_one

    def _work_rules(
        self, q: Q, agent_id: str, work_input: WorkInput, searches_left: int
    ) -> Callable[[WorkOutput], list[str]]:
        passages = {p.passage_id: p.file_id for p in work_input.passages}

        def rules(out: WorkOutput) -> list[str]:
            def run(conn: sqlite3.Connection) -> list[str]:
                errors = validators.unknown_ids(out, work_input)
                return errors + validators.work(out, searches_left, self._quote_check(conn, q, agent_id, passages))

            return self._with_conn(run, write=False)

        return rules

    def _cite(self, conn: sqlite3.Connection, q: Q, agent_id: str, turn_id: str, quote: Quote) -> str:
        if quote.citation_id is not None:
            q.number(quote.citation_id)
            return quote.citation_id
        assert quote.passage_id is not None and quote.quote is not None
        row = create_citation(conn, self._agent_ctx(q, agent_id), workspace_id=q.workspace_id, passage_id=quote.passage_id,
                              quote=quote.quote, agent_id=agent_id, turn_id=turn_id)  # fmt: skip
        q.number(row.id)
        return row.id

    def _say(
        self, conn: sqlite3.Connection, q: Q, agent_id: str, text: str, citation_ids: list[str], turn_id: str | None
    ) -> None:
        if turn_id is not None:
            huddle.add_statement(conn, workspace_id=q.workspace_id, question_id=q.question_id, round_id=q.round_id,
                                 turn_id=turn_id, agent_id=agent_id, text=text, citation_ids=citation_ids)  # fmt: skip
        wire = [self._citation(conn, q, c) for c in citation_ids]
        self._emit(conn, q, agent_id, "huddle.statement",
                   SayEvent(agent_id=self._wire_agent(q, agent_id), text=text, citations=wire or None),
                   payload={"text": text, "citation_ids": citation_ids})  # fmt: skip
        name = "Orchestrator" if agent_id == q.orchestrator else q.translators.get(agent_id, agent_id)
        q.transcript.append(
            Line(agent=name, text=text, citations=[inputs.citation_in(conn, c, q.numbers[c]) for c in citation_ids])
        )

    def _store_work(
        self, conn: sqlite3.Connection, q: Q, agent_id: str, turn_id: str, out: WorkOutput, by_passage: dict[str, str]
    ) -> None:
        # Every quote was checked while validating the turn, so creating the citations cannot be rejected here.
        for statement in out.statements:
            cited = list(dict.fromkeys(self._cite(conn, q, agent_id, turn_id, quote) for quote in statement.quotes))
            self._say(conn, q, agent_id, statement.text, cited, turn_id)
        for note in out.notes:
            cited = list(dict.fromkeys(self._cite(conn, q, agent_id, turn_id, quote) for quote in note.quotes))
            create_agent_note(
                conn, self._agent_ctx(q, agent_id), workspace_id=q.workspace_id, file_id=note.file_id, author_id=agent_id,
                kind=note.kind, text=note.text, citation_ids=cited, numbers=[q.numbers[c] for c in cited],
                question_id=q.question_id, turn_id=turn_id,
            )  # fmt: skip
        nodes, links = add_mentions(conn, self._agent_ctx(q, agent_id), workspace_id=q.workspace_id,
                                    entities=out.entities, passage_file=lambda p: by_passage[p],
                                    question_id=q.question_id)  # fmt: skip
        q.nodes += nodes
        q.links += links

    # --- review ----------------------------------------------------------------------------------------------

    async def _review(self, q: Q, state: QState, failed: tuple[FailedClaim, ...]) -> ReviewDone:
        files, agents, _, _ = await self._db(lambda c: self._context(c, q), write=False)
        steps_left = max(0, state.max_steps - state.steps)
        review_input = ReviewInput(
            question=q.text, transcript=list(q.transcript), members=sorted(state.members), agents=agents, files=files,
            failed=[FailedClaimIn(claim_text=f.text, verdict=f.verdict, reason=f.reason) for f in failed],
            steps_left=steps_left,
        )  # fmt: skip
        translators = set(q.translators)

        def rules(out: ReviewOutput) -> list[str]:
            return validators.unknown_ids(out, review_input) + validators.review(
                out, steps_left, set(state.members), translators
            )

        q.review, _ = await self.runner.run(
            self._agent_ctx(q, q.orchestrator), agent_id=q.orchestrator, turn_type="review", input=review_input,
            output_model=ReviewOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
        )  # fmt: skip
        followups = tuple(
            Assignment(f.agent_id, tuple(f.file_ids) or tuple(q.files_of.get(f.agent_id, [])), f.focus,
                       "volunteered" if f.agent_id in state.members else "called")
            for f in q.review.followups
        )  # fmt: skip
        return ReviewDone(q.review.decision, followups)

    # --- claims and verification -----------------------------------------------------------------------------

    def _known_citations(self, conn: sqlite3.Connection, q: Q) -> set[str]:
        known: set[str] = set()
        for cid in q.numbers:
            row = citations_repo.get(conn, cid)
            current = files_repo.get(conn, q.workspace_id, row.file_id) if row is not None else None
            if row is not None and current is not None and current["file_version_id"] == row.file_version_id:
                known.add(cid)
        return known

    async def _draft(self, q: Q) -> ClaimsDrafted:
        draft_input = DraftClaimsInput(question=q.text, transcript=list(q.transcript), earlier=list(q.earlier))
        known = await self._db(lambda c: self._known_citations(c, q), write=False)

        def rules(out: DraftClaimsOutput) -> list[str]:
            return validators.unknown_ids(out, draft_input) + claim_rules.validate_claims(out.claims, known)

        out, turn_id = await self.runner.run(
            self._agent_ctx(q, q.orchestrator), agent_id=q.orchestrator, turn_type="draft_claims", input=draft_input,
            output_model=DraftClaimsOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
        )  # fmt: skip
        assert q.round_id is not None
        round_id = q.round_id
        q.round_claims = await self._db(lambda c: claim_rules.store_claims(
            c, self._agent_ctx(q, q.orchestrator), question_id=q.question_id, round_id=round_id, turn_id=turn_id,
            claims=out.claims,
        ))  # fmt: skip
        return ClaimsDrafted(len(q.round_claims))

    def _claim_wire(self, q: Q, row: ClaimRow) -> Claim:
        return Claim.model_validate({
            "id": row.id, "text": row.text, "kind": row.kind, "citations": [q.number(c) for c in row.citation_ids],
            "derivedFrom": list(row.input_ids) or None, "calculation": row.expression,
        })  # fmt: skip

    def _emit_verify(self, conn: sqlite3.Connection, q: Q) -> None:
        cited = list(dict.fromkeys(c for row in q.round_claims for c in row.citation_ids))
        event = VerifyEvent(
            round=q.round_no, claims=[self._claim_wire(q, r) for r in q.round_claims],
            citations=[self._citation(conn, q, c) for c in cited],
        )  # fmt: skip
        self._emit(
            conn, q, q.verifier, "verification.started", event, payload={"claim_ids": [r.id for r in q.round_claims]}
        )

    async def _verify(self, q: Q) -> Verified:
        def mechanical(conn: sqlite3.Connection) -> dict[str, VerdictRow]:
            found: dict[str, VerdictRow] = {}
            for row in q.round_claims:
                if row.carried is not None:
                    found[row.id] = VerdictRow(row.id, row.carried.verdict, row.carried.reason, row.carried.verdict_id)
                    continue
                broken = [c for c in row.citation_ids if not check(conn, c).ok]
                if row.arithmetic_error is not None:
                    found[row.id] = VerdictRow(
                        row.id, "mechanical_fail", f"The calculation does not hold: {row.arithmetic_error}."
                    )
                elif broken:
                    found[row.id] = VerdictRow(
                        row.id, "mechanical_fail", "A cited passage failed the mechanical check."
                    )
            return found

        verdicts = await self._db(mechanical, write=False)
        to_check = [r for r in q.round_claims if r.id not in verdicts]
        turn_id: str | None = None
        if to_check:
            verify_input = await self._db(
                lambda c: VerifyInput(claims=[self._claim_in(c, q, r) for r in to_check]), write=False
            )

            def rules(out: VerifyOutput) -> list[str]:
                return validators.unknown_ids(out, verify_input) + validators.verify(out, verify_input)

            out, turn_id = await self.runner.run(
                self._agent_ctx(q, q.verifier), agent_id=q.verifier, turn_type="verify", input=verify_input,
                output_model=VerifyOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
            )  # fmt: skip
            for v in out.verdicts:
                verdicts[v.claim_id] = VerdictRow(v.claim_id, v.verdict, v.reason,
                                                  supports=tuple((c.citation_id, c.supports) for c in v.citations))  # fmt: skip
        q.verdicts = {r.id: verdicts[r.id] for r in q.round_claims}
        passed = claim_rules.passes([v.verdict for v in q.verdicts.values()])
        assert q.round_id is not None
        round_id, check_turn = q.round_id, turn_id
        await self._db(lambda c: verifications_repo.insert(
            c, verification_id=new_id("v"), workspace_id=q.workspace_id, question_id=q.question_id, round_id=round_id,
            turn_id=check_turn, passed=passed, verdicts=list(q.verdicts.values()),
        ))  # fmt: skip
        q.earlier = [EarlierClaim(ref=r.ref, text=r.text, verdict=q.verdicts[r.id].verdict, reason=q.verdicts[r.id].reason)
                     for r in q.round_claims]  # fmt: skip
        failed = tuple(FailedClaim(r.id, r.text, q.verdicts[r.id].verdict, q.verdicts[r.id].reason)
                       for r in q.round_claims if q.verdicts[r.id].verdict != "supported")  # fmt: skip
        return Verified(passed, failed)

    def _claim_in(self, conn: sqlite3.Connection, q: Q, row: ClaimRow) -> ClaimIn:
        inputs_rows = [r for r in q.round_claims if r.id in row.input_ids]
        return ClaimIn.model_validate({
            "claimId": row.id, "text": row.text, "kind": row.kind,
            "citations": [inputs.citation_in(conn, c, q.number(c)) for c in row.citation_ids],
            "inputs": [ClaimRef(claim_id=r.id, text=r.text) for r in inputs_rows],
            "expression": row.expression, "computedResult": row.computed_result,
        })  # fmt: skip

    def _emit_verdict(self, conn: sqlite3.Connection, q: Q) -> None:
        verdicts = [Verdict.model_validate({"claimId": v.claim_id, "verdict": v.verdict, "reason": v.reason})
                    for v in q.verdicts.values()]  # fmt: skip
        passed = claim_rules.passes([v.verdict for v in verdicts])
        self._emit(conn, q, q.verifier, "verification.completed", VerdictEvent(round=q.round_no, passed=passed, verdicts=verdicts),
                   payload={"passed": passed, "verdicts": [v.model_dump(mode="json") for v in verdicts]})  # fmt: skip

    def _rehuddle(self, conn: sqlite3.Connection, q: Q, round_no: int, failed: tuple[FailedClaim, ...]) -> None:
        reason = " ".join(f.reason for f in failed) or "Verification failed."
        self._emit(conn, q, q.orchestrator, "huddle.reopened",
                   RehuddleEvent(round=round_no, reason=reason, claim_ids=[f.claim_id for f in failed]),
                   payload={"round": round_no})  # fmt: skip

    # --- the answer ------------------------------------------------------------------------------------------

    async def _write(self, q: Q, mode: str) -> AnswerWritten:
        supported = [r for r in q.round_claims if q.verdicts.get(r.id) and q.verdicts[r.id].verdict == "supported"]
        claims = [ClaimRef(claim_id=r.id, text=r.text) for r in supported] if mode in ("full", "partial") else []
        if mode == "partial":
            q.unverified = [
                Unverified(text=r.text, reason=q.verdicts[r.id].reason) for r in q.round_claims if r not in supported
            ]
        history = await self._db(lambda c: inputs.history(c, q.session_id, q.question_id), write=False)
        write_input = WriteAnswerInput.model_validate(
            {"question": q.text, "history": history, "mode": mode, "claims": claims, "unverified": q.unverified}
        )
        verified = {c.claim_id: c.text for c in claims}
        claim_citations = {r.id: list(r.citation_ids) for r in supported}

        def rules(out: WriteAnswerOutput) -> list[str]:
            return validators.unknown_ids(out, write_input) + claim_rules.validate_segments(
                out.segments, verified, mode
            )

        try:
            out, _ = await self.runner.run(
                self._agent_ctx(q, q.chat), agent_id=q.chat, turn_type="write_answer", input=write_input,
                output_model=WriteAnswerOutput, validate=rules, question_id=q.question_id, round_id=q.round_id,
            )  # fmt: skip
            q.answer_text, q.answer_citations = claim_rules.assemble_answer(out.segments, claim_citations)
            q.answer_claims = list(dict.fromkeys(c for s in out.segments for c in s.claim_ids))
        except TurnFailed:
            if claims:
                q.answer_text, q.answer_citations = claim_rules.fallback_answer(claims, claim_citations)
                q.answer_claims = [c.claim_id for c in claims]
            else:
                q.answer_text = NO_FILES if mode == "no_files" else NOTHING_FOUND
        return AnswerWritten()

    def _answer(self, conn: sqlite3.Connection, q: Q) -> None:
        chat = self._agent_ctx(q, q.chat)
        message_id = add_message(conn, chat, workspace_id=q.workspace_id, session_id=q.session_id, role="assistant",
                                 text=q.answer_text, question_id=q.question_id, citation_ids=q.answer_citations,
                                 unverified=q.unverified or None)  # fmt: skip
        conn.executemany("INSERT INTO message_claims (message_id, claim_id) VALUES (?, ?)",
                         [(message_id, c) for c in q.answer_claims])  # fmt: skip
        cited = [citations_repo.to_wire(conn, c, n) for n, c in enumerate(q.answer_citations, start=1)]
        event = AnswerEvent(text=q.answer_text, citations=cited, unverified=q.unverified or None)
        self._emit(conn, q, q.chat, "answer.written", event, entity_type="message", entity_id=message_id)

    def _complete(self, conn: sqlite3.Connection, q: Q, state: QState) -> None:
        huddle.end_rounds(conn, q.question_id)
        tokens_in, tokens_out = questions_repo.finish(conn, q.question_id, state=state.name)
        started = questions_repo.by_id(conn, q.question_id)
        assert started is not None
        seconds = conn.execute(
            "SELECT (julianday(finished_at) - julianday(started_at)) * 86400.0 FROM questions WHERE id = ?",
            (q.question_id,),
        ).fetchone()[0]
        self._emit(conn, q, "system", "question.completed", payload={
            "state": state.name, "rounds": q.round_no, "input_tokens": tokens_in, "output_tokens": tokens_out,
            "seconds": round(seconds or 0.0, 3),
        })  # fmt: skip

    async def _cancel_turns(self, q: Q) -> None:
        def cancel(conn: sqlite3.Connection) -> list[str]:
            ids: list[str] = []
            for turn in questions_repo.open_turns(conn, q.question_id):
                turns_repo.finish(conn, turn["id"], state="cancelled", error="question ended")
                self._emit(conn, q, turn["agent_id"], "turn.cancelled", turn_id=turn["id"], entity_type="turn",
                           entity_id=turn["id"], definition_version_id=turn["definition_version_id"])  # fmt: skip
                ids.append(turn["id"])
            return ids

        for turn_id in await self._db(cancel):
            await self.runner.runtime.cancel(turn_id)

    def _cancelled(self, conn: sqlite3.Connection, q: Q) -> None:
        huddle.end_rounds(conn, q.question_id)
        questions_repo.finish(conn, q.question_id, state="cancelled")
        by = q.cancel_ctx or q.ctx
        self._emit(conn, q, by.actor_id, "question.cancelled", CancelledEvent(), source=by.source)

    def _error(self, conn: sqlite3.Connection, q: Q, code: str, message: str) -> None:
        huddle.end_rounds(conn, q.question_id)
        questions_repo.finish(conn, q.question_id, state="failed", error_code=code, error_message=message)
        self._emit(conn, q, "system", "question.failed", ErrorEvent(code=code, message=message), payload={"code": code})
