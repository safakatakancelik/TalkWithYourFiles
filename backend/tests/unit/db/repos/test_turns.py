import sqlite3

from twyf.contract.models import Workspace
from twyf.contract.operations import CreateWorkspaceInput
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import turns as repo
from twyf.recording.context import RequestContext
from twyf.services import workspaces


def _insert(conn: sqlite3.Connection, ws: Workspace, turn_id: str) -> None:
    agent = agents_repo.builtin(conn, ws.id, "verifier")
    dv = conn.execute(
        "SELECT id FROM agent_definition_versions WHERE definition_id = ?", (agent.definition_id,)
    ).fetchone()[0]
    with transaction(conn):
        repo.insert(
            conn, turn_id=turn_id, workspace_id=ws.id, question_id=None, round_id=None, agent_id=agent.id,
            agent_version_id=agent.agent_version_id, definition_version_id=dv, turn_type="verify", attempt=1,
            retry_of=None, runtime="fake", system_prompt="s", input={"claims": []},
        )  # fmt: skip


def test_create_and_get(ws: Workspace, conn: sqlite3.Connection) -> None:
    _insert(conn, ws, "t_1")
    row = repo.get(conn, ws.id, "t_1")
    assert row is not None and (row["state"], row["turn_type"], row["input"]) == ("queued", "verify", '{"claims": []}')
    with transaction(conn):
        repo.finish(
            conn,
            "t_1",
            state="done",
            output={"verdicts": []},
            model="m",
            input_tokens=1,
            output_tokens=2,
            duration_ms=3,
        )
    row = repo.get(conn, ws.id, "t_1")
    assert row is not None and (row["state"], row["output"], row["duration_ms"]) == ("done", '{"verdicts": []}', 3)


def test_workspace_isolation(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    _insert(conn, ws, "t_1")
    assert repo.get(conn, other.id, "t_1") is None
