import sqlite3

from twyf.agents.definitions import current_version, resolve
from twyf.contract.models import Agent, TranslatorReply
from twyf.contract.operations import (
    AskTranslatorInput,
    CreateAgentInput,
    DeleteAgentInput,
    ListAgentsInput,
    RenameAgentInput,
)
from twyf.db.connection import transaction
from twyf.db.repos import agents as repo
from twyf.db.repos import huddle
from twyf.db.repos.agents import AgentRow
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
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


async def ask_translator(ctx: RequestContext, input: AskTranslatorInput) -> TranslatorReply:
    raise ServiceError("internal", "not implemented")
