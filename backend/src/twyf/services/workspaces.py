import sqlite3

from twyf.agents.definitions import current_version, resolve
from twyf.contract.models import Workspace
from twyf.contract.operations import (
    CreateWorkspaceInput,
    DeleteWorkspaceInput,
    ListWorkspacesInput,
    RenameWorkspaceInput,
)
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import workspaces as repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text

BUILTIN_AGENTS = [
    ("orchestrator", "Orchestrator", ""),
    ("verifier", "Verifier", ""),
    ("chat", "Chat", ""),
    ("translator", "Translator 1", "generic"),
    ("translator", "Translator 2", "generic"),
]


def require(conn: sqlite3.Connection, ws_id: str) -> None:
    if repo.get(conn, ws_id) is None:
        raise ServiceError("not_found", "No such workspace", {"ws": ws_id})


def _wire(row: sqlite3.Row) -> Workspace:
    return Workspace(id=row["id"], name=row["name"])


def list(ctx: RequestContext, input: ListWorkspacesInput) -> list[Workspace]:
    with state.db() as conn:
        return [_wire(r) for r in repo.list(conn, ctx.user_id)]


def create(ctx: RequestContext, input: CreateWorkspaceInput) -> Workspace:
    name = require_text(input.name, "name")
    ws_id = new_id("ws")
    with state.db() as conn, transaction(conn):
        repo.insert(conn, ws_id, ctx.user_id, name)
        event_id = record(
            conn, ctx, "workspace.created", workspace_id=ws_id, entity_type="workspace", entity_id=ws_id,
            payload={"name": name},
        )  # fmt: skip
        system = ctx.as_actor("system").caused_by(event_id)
        for kind, agent_name, specialty in BUILTIN_AGENTS:
            definition_id = resolve(conn, kind, specialty or kind)
            agent_id = new_id("a")
            agents_repo.insert(conn, ws_id, agent_id, kind, agent_name, specialty, definition_id)
            record(
                conn, system, "agent.created", workspace_id=ws_id, entity_type="agent", entity_id=agent_id,
                payload={"kind": kind, "name": agent_name, "specialty": specialty},
                definition_version_id=current_version(conn, definition_id).id,
            )  # fmt: skip
        return Workspace(id=ws_id, name=name)


def rename(ctx: RequestContext, input: RenameWorkspaceInput) -> Workspace:
    name = require_text(input.name, "name")
    with state.db() as conn, transaction(conn):
        row = repo.get(conn, input.ws)
        if row is None:
            raise ServiceError("not_found", "No such workspace", {"ws": input.ws})
        repo.rename(conn, input.ws, name)
        record(
            conn, ctx, "workspace.renamed", workspace_id=input.ws, entity_type="workspace", entity_id=input.ws,
            payload={"old": row["name"], "new": name},
        )  # fmt: skip
        return Workspace(id=input.ws, name=name)


def delete(ctx: RequestContext, input: DeleteWorkspaceInput) -> None:
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        repo.soft_delete(conn, input.ws)
        record(conn, ctx, "workspace.deleted", workspace_id=input.ws, entity_type="workspace", entity_id=input.ws)
