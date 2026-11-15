import sqlite3

import pytest

from tests.conftest import EventsHelper
from twyf.contract.models import Agent, Workspace
from twyf.contract.operations import CreateAgentInput, DeleteAgentInput, ListAgentsInput, RenameAgentInput
from twyf.recording.context import RequestContext
from twyf.services import agents
from twyf.services.errors import ServiceError


def _slug(conn: sqlite3.Connection, agent_id: str) -> str:
    return conn.execute(
        "SELECT d.slug FROM v_agents a JOIN agent_definitions d ON d.id = a.definition_id WHERE a.id = ?", (agent_id,)
    ).fetchone()[0]


def test_list_is_translators_only(ws: Workspace, ctx: RequestContext) -> None:
    listed = agents.list(ctx, ListAgentsInput(ws=ws.id))
    assert [(a.name, a.specialty) for a in listed] == [("Translator 1", "generic"), ("Translator 2", "generic")]


def test_create_resolves_definition(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    lawyer = agents.create(ctx, CreateAgentInput(ws=ws.id, name="Lawyer", specialty="contracts"))
    poet = agents.create(ctx, CreateAgentInput(ws=ws.id, name="Poet", specialty="poetry"))
    assert lawyer == Agent(id=lawyer.id, name="Lawyer", specialty="contracts")
    assert _slug(conn, lawyer.id) == "translator-contracts"
    assert _slug(conn, poet.id) == "translator"
    assert [a.name for a in agents.list(ctx, ListAgentsInput(ws=ws.id))][-2:] == ["Lawyer", "Poet"]


def test_rename_and_delete(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    first = agents.list(ctx, ListAgentsInput(ws=ws.id))[0]
    renamed = agents.rename(ctx, RenameAgentInput(ws=ws.id, agent_id=first.id, name="Reader"))
    assert renamed.name == "Reader"
    assert events("agent.renamed")[0].payload == {"old": "Translator 1", "new": "Reader"}
    agents.delete(ctx, DeleteAgentInput(ws=ws.id, agent_id=first.id))
    assert first.id not in [a.id for a in agents.list(ctx, ListAgentsInput(ws=ws.id))]
    assert conn.execute("SELECT deleted_at FROM agents WHERE id = ?", (first.id,)).fetchone()[0] is not None
    with pytest.raises(ServiceError) as raised:
        agents.rename(ctx, RenameAgentInput(ws=ws.id, agent_id=first.id, name="Again"))
    assert raised.value.code == "not_found"


def test_builtins_cannot_be_changed(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    for kind in ("orchestrator", "verifier", "chat"):
        agent = agents.builtin(conn, ws.id, kind)
        with pytest.raises(ServiceError) as raised:
            agents.rename(ctx, RenameAgentInput(ws=ws.id, agent_id=agent.id, name="x"))
        assert raised.value.code == "validation"
        with pytest.raises(ServiceError) as raised:
            agents.delete(ctx, DeleteAgentInput(ws=ws.id, agent_id=agent.id))
        assert raised.value.code == "validation"


def test_agent_from_another_workspace_is_not_found(ws: Workspace, ctx: RequestContext) -> None:
    from twyf.contract.operations import CreateWorkspaceInput
    from twyf.services import workspaces

    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    theirs = agents.list(ctx, ListAgentsInput(ws=other.id))[0]
    with pytest.raises(ServiceError) as raised:
        agents.rename(ctx, RenameAgentInput(ws=ws.id, agent_id=theirs.id, name="x"))
    assert raised.value.code == "not_found"
