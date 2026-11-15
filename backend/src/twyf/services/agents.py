import asyncio
import builtins
import sqlite3
from collections.abc import Callable

from twyf.agents.definitions import current_version, resolve
from twyf.citations.locate import create_citation
from twyf.contract.models import Agent, TranslatorReply
from twyf.contract.operations import (
    AskTranslatorInput,
    CreateAgentInput,
    DeleteAgentInput,
    ListAgentsInput,
    RenameAgentInput,
)
from twyf.contract.turns import DirectReplyInput, DirectReplyOutput, NoteIn, PassageIn
from twyf.db.connection import transaction
from twyf.db.repos import agents as repo
from twyf.db.repos import citations as citations_repo
from twyf.db.repos import files as files_repo
from twyf.db.repos import huddle
from twyf.db.repos.agents import AgentRow
from twyf.files.integrity import verify_workspace
from twyf.ids import new_id
from twyf.orchestration import validators
from twyf.orchestration.inputs import usable_ready_files
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval.weights import notes_for_turn
from twyf.runtime.runner import TurnFailed
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.notes import create_agent_note
from twyf.services.workspaces import require


def builtin(conn: sqlite3.Connection, ws_id: str, kind: str) -> AgentRow:
    return repo.builtin(conn, ws_id, kind)


def _wire(agent: AgentRow) -> Agent:
    return Agent(id=agent.id, name=agent.name, specialty=agent.specialty)


def _translator(conn: sqlite3.Connection, ws_id: str, agent_id: str) -> AgentRow:
    agent = repo.get(conn, ws_id, agent_id)
    if agent is None:
        raise ServiceError("not_found", "No such agent", {"agent_id": agent_id})
    if agent.agent_kind != "translator":
        raise ServiceError("validation", f"The {agent.agent_kind} cannot be changed", {"agent_id": agent_id})
    if huddle.running_members(conn, agent_id):
        raise ServiceError("conflict", "The agent is in a running huddle", {"agent_id": agent_id})
    return agent


def list(ctx: RequestContext, input: ListAgentsInput) -> list[Agent]:
    with state.db() as conn:
        require(conn, input.ws)
        return [_wire(a) for a in repo.list(conn, input.ws, "translator")]


def create(ctx: RequestContext, input: CreateAgentInput) -> Agent:
    name = require_text(input.name, "name")
    specialty = input.specialty.strip() or "generic"
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        definition_id = resolve(conn, "translator", specialty)
        agent_id = new_id("a")
        repo.insert(conn, input.ws, agent_id, "translator", name, specialty, definition_id)
        record(
            conn, ctx, "agent.created", workspace_id=input.ws, entity_type="agent", entity_id=agent_id,
            payload={"kind": "translator", "name": name, "specialty": specialty},
            definition_version_id=current_version(conn, definition_id).id,
        )  # fmt: skip
        return Agent(id=agent_id, name=name, specialty=specialty)


def rename(ctx: RequestContext, input: RenameAgentInput) -> Agent:
    name = require_text(input.name, "name")
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        agent = _translator(conn, input.ws, input.agent_id)
        repo.set_version(conn, agent, name=name)
        record(
            conn, ctx, "agent.renamed", workspace_id=input.ws, entity_type="agent", entity_id=agent.id,
            payload={"old": agent.name, "new": name},
        )  # fmt: skip
        return Agent(id=agent.id, name=name, specialty=agent.specialty)


def delete(ctx: RequestContext, input: DeleteAgentInput) -> None:
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        agent = _translator(conn, input.ws, input.agent_id)
        repo.soft_delete(conn, agent.id)
        record(conn, ctx, "agent.deleted", workspace_id=input.ws, entity_type="agent", entity_id=agent.id)


def _notes(ws: str, file_ids: builtins.list[str], query: str) -> builtins.list[NoteIn]:
    with state.db() as conn:
        return notes_for_turn(conn, workspace_id=ws, file_ids=file_ids, query=query)


def _reply_rules(
    agent_ctx: RequestContext, ws: str, passages: dict[str, str], reply_input: DirectReplyInput, searches_left: int
) -> Callable[[DirectReplyOutput], builtins.list[str]]:
    def rules(out: DirectReplyOutput) -> builtins.list[str]:
        with state.db() as conn:
            check = validators.passage_quote_check(conn, agent_ctx, ws, passages)
            return validators.unknown_ids(out, reply_input) + validators.work(out, searches_left, check)

    return rules


async def ask_translator(ctx: RequestContext, input: AskTranslatorInput) -> TranslatorReply:
    """A direct chat: a `direct_reply` turn with the search loop. Cited, mechanically checked, not verified."""
    question = require_text(input.question, "question")
    engine = state.engine()
    settings, runner, retriever = engine.settings, engine.runner, engine.retriever

    def begin() -> AgentRow:
        with state.db() as conn, transaction(conn):
            require(conn, input.ws)
            agent = repo.get(conn, input.ws, input.agent_id)
            if agent is None or agent.agent_kind != "translator":
                raise ServiceError("not_found", "No such translator", {"agent_id": input.agent_id})
            record(conn, ctx, "translator.asked", workspace_id=input.ws, entity_type="agent", entity_id=agent.id,
                   payload={"question": question})  # fmt: skip
            return agent

    agent = await asyncio.to_thread(begin)
    agent_ctx = ctx.as_actor(agent.id)

    def usable() -> builtins.list[str]:
        with state.db() as conn:
            verify_workspace(conn, ctx, input.ws)
            return [r["id"] for r in usable_ready_files(conn, input.ws)]

    file_ids = await asyncio.to_thread(usable)
    passages = await asyncio.to_thread(retriever.search, agent_ctx, workspace_id=input.ws, query=question,
                                       file_ids=file_ids, k=settings.passages_per_turn)  # fmt: skip
    searches_left = settings.searches_per_turn
    while True:
        touched = builtins.list(dict.fromkeys(p.file_id for p in passages))
        reply_input = DirectReplyInput(
            question=question, notes=await asyncio.to_thread(_notes, input.ws, touched, question),
            searches_left=searches_left,
            passages=[PassageIn(passage_id=p.passage_id, file_id=p.file_id, file_name=p.file_name, location=p.location,
                                text=p.text) for p in passages],
        )  # fmt: skip
        rules = _reply_rules(
            agent_ctx, input.ws, {p.passage_id: p.file_id for p in passages}, reply_input, searches_left
        )
        try:
            out, turn_id = await runner.run(agent_ctx, agent_id=agent.id, turn_type="direct_reply", input=reply_input,
                                            output_model=DirectReplyOutput, validate=rules)  # fmt: skip
        except TurnFailed as failed:
            raise ServiceError("internal", "The translator could not answer.", {"reason": failed.reason}) from failed
        if not out.searches or searches_left <= 0:
            break
        seen = {p.chunk_id for p in passages}
        for search in out.searches[:searches_left]:
            targets = [search.file_id] if search.file_id in file_ids else file_ids
            found = await asyncio.to_thread(retriever.search, agent_ctx, workspace_id=input.ws, query=search.query,
                                            file_ids=targets, k=settings.passages_per_turn)  # fmt: skip
            passages += [p for p in found if p.chunk_id not in seen]
            seen |= {p.chunk_id for p in found}
            searches_left -= 1

    def store() -> TranslatorReply:
        with state.db() as conn, transaction(conn):
            for file_id in dict.fromkeys(p.file_id for p in passages):
                current = files_repo.get(conn, input.ws, file_id)
                if current is not None:
                    huddle.assign(conn, workspace_id=input.ws, question_id=None, round_id=None, agent_id=agent.id,
                                  file_id=file_id, file_version_id=current["file_version_id"], purpose="direct")  # fmt: skip
                    record(conn, agent_ctx, "huddle.file_assigned", workspace_id=input.ws, entity_type="file",
                           entity_id=file_id, payload={"agent_id": agent.id, "purpose": "direct"})  # fmt: skip
            order: builtins.list[str] = []
            texts: builtins.list[str] = []
            for statement in out.statements:
                cited = [create_citation(conn, agent_ctx, workspace_id=input.ws, passage_id=q.passage_id or "",
                                         quote=q.quote or "", agent_id=agent.id, turn_id=turn_id).id
                         for q in statement.quotes]  # fmt: skip
                huddle.add_statement(conn, workspace_id=input.ws, question_id=None, round_id=None, turn_id=turn_id,
                                     agent_id=agent.id, text=statement.text, citation_ids=cited)  # fmt: skip
                order += [c for c in cited if c not in order]
                texts.append(statement.text)
            for note in out.notes:
                cited = [create_citation(conn, agent_ctx, workspace_id=input.ws, passage_id=q.passage_id or "",
                                         quote=q.quote or "", agent_id=agent.id, turn_id=turn_id).id
                         for q in note.quotes]  # fmt: skip
                create_agent_note(conn, agent_ctx, workspace_id=input.ws, file_id=note.file_id, author_id=agent.id,
                                  kind=note.kind, text=note.text, citation_ids=builtins.list(dict.fromkeys(cited)), numbers=[],
                                  question_id=None, turn_id=turn_id)  # fmt: skip
            text = " ".join(texts)
            reply = TranslatorReply(
                text=text, citations=[citations_repo.to_wire(conn, c, n) for n, c in enumerate(order, 1)]
            )
            record(conn, agent_ctx, "translator.replied", workspace_id=input.ws, turn_id=turn_id, entity_type="agent",
                   entity_id=agent.id, payload={"text": text, "citation_ids": order})  # fmt: skip
            return reply

    return await asyncio.to_thread(store)
