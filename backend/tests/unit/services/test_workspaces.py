import sqlite3

import pytest

from tests.conftest import EventsHelper
from twyf.contract.models import Workspace
from twyf.contract.operations import (
    CreateWorkspaceInput,
    DeleteWorkspaceInput,
    ListAgentsInput,
    ListWorkspacesInput,
    RenameWorkspaceInput,
)
from twyf.recording.context import RequestContext
from twyf.services import agents, workspaces
from twyf.services.errors import ServiceError
from twyf.services.mapping import actor_to_wire


def test_create_makes_builtin_agents(ws: Workspace, conn: sqlite3.Connection, events: EventsHelper) -> None:
    kinds = conn.execute(
        "SELECT agent_kind, name, specialty FROM v_agents WHERE workspace_id = ? ORDER BY created_at, name", (ws.id,)
    ).fetchall()
    assert sorted(tuple(k) for k in kinds) == [
        ("chat", "Chat", ""), ("orchestrator", "Orchestrator", ""),
        ("translator", "Translator", "generic"),
        ("verifier", "Verifier", ""),
    ]  # fmt: skip
    [created] = events("workspace.created")
    assert (created.actor_id, created.source, created.entity_id) == ("u_local", "api", ws.id)
    agent_events = events("agent.created")
    assert len(agent_events) == 4
    assert all(
        e.actor_id == "system" and e.source == "internal" and e.cause_event_id == created.id for e in agent_events
    )
    assert all(
        conn.execute("SELECT agent_definition_version_id FROM app_events WHERE id = ?", (e.id,)).fetchone()[0]
        for e in agent_events
    )


def test_list_rename_delete(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    assert workspaces.list(ctx, ListWorkspacesInput()) == [ws]
    renamed = workspaces.rename(ctx, RenameWorkspaceInput(ws=ws.id, name="New name"))
    assert renamed == Workspace(id=ws.id, name="New name")
    assert events("workspace.renamed")[0].payload == {"old": "Test workspace", "new": "New name"}
    workspaces.delete(ctx, DeleteWorkspaceInput(ws=ws.id))
    assert workspaces.list(ctx, ListWorkspacesInput()) == []
    assert conn.execute("SELECT COUNT(*) FROM workspaces WHERE id = ?", (ws.id,)).fetchone()[0] == 1
    for call in (
        lambda: workspaces.rename(ctx, RenameWorkspaceInput(ws=ws.id, name="x")),
        lambda: workspaces.delete(ctx, DeleteWorkspaceInput(ws=ws.id)),
        lambda: agents.list(ctx, ListAgentsInput(ws=ws.id)),
    ):
        with pytest.raises(ServiceError) as raised:
            call()
        assert raised.value.code == "not_found"


def test_empty_name_is_validation(synced: None, ctx: RequestContext) -> None:
    with pytest.raises(ServiceError) as raised:
        workspaces.create(ctx, CreateWorkspaceInput(name="  "))
    assert raised.value.code == "validation"


def test_require(ws: Workspace, conn: sqlite3.Connection) -> None:
    workspaces.require(conn, ws.id)
    with pytest.raises(ServiceError):
        workspaces.require(conn, "ws_nope")


def test_actor_to_wire(ws: Workspace, conn: sqlite3.Connection) -> None:
    orchestrator = agents.builtin(conn, ws.id, "orchestrator")
    verifier = agents.builtin(conn, ws.id, "verifier")
    chat = agents.builtin(conn, ws.id, "chat")
    assert actor_to_wire(conn, ws.id, orchestrator.id) == "orchestrator"
    assert actor_to_wire(conn, ws.id, verifier.id) == "verifier"
    assert actor_to_wire(conn, ws.id, "u_local") == "user"
    assert actor_to_wire(conn, ws.id, chat.id) == chat.id
