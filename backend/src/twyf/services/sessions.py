import builtins
import json
import sqlite3
from collections.abc import Sequence

from twyf.contract.models import ChatMsg, Session, Unverified, dump
from twyf.contract.operations import (
    CreateSessionInput,
    DeleteSessionInput,
    GetMessagesInput,
    ListSessionsInput,
    RenameSessionInput,
)
from twyf.db.connection import transaction
from twyf.db.repos import citations as citations_repo
from twyf.db.repos import questions as questions_repo
from twyf.db.repos import sessions as repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.workspaces import require


def _wire(row: sqlite3.Row) -> Session:
    return Session(id=row["id"], title=row["title"], updated_at=row["updated_at"], message_count=row["message_count"])


def live(conn: sqlite3.Connection, ws_id: str, session_id: str) -> sqlite3.Row:
    row = repo.get(conn, ws_id, session_id)
    if row is None:
        raise ServiceError("not_found", "No such session", {"session_id": session_id})
    return row


def add_message(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    *,
    workspace_id: str,
    session_id: str,
    role: str,
    text: str,
    question_id: str | None = None,
    citation_ids: Sequence[str] = (),
    unverified: builtins.list[Unverified] | None = None,
) -> str:
    """Stores a message with its citations numbered from 1, inside the caller's transaction."""
    message_id = repo.insert_message(
        conn, message_id=new_id("m"), workspace_id=workspace_id, session_id=session_id, role=role, text=text,
        question_id=question_id, citation_ids=builtins.list(citation_ids),
        unverified=[dump(u) for u in unverified] if unverified is not None else None,
    )  # fmt: skip
    record(
        conn, ctx, "message.created", workspace_id=workspace_id, session_id=session_id, question_id=question_id,
        entity_type="message", entity_id=message_id, payload={"role": role},
    )  # fmt: skip
    return message_id


def list(ctx: RequestContext, input: ListSessionsInput) -> builtins.list[Session]:
    with state.db() as conn:
        require(conn, input.ws)
        return [_wire(r) for r in repo.list(conn, input.ws)]


def create(ctx: RequestContext, input: CreateSessionInput) -> Session:
    title = require_text(input.title, "title")
    session_id = new_id("s")
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        repo.insert(conn, input.ws, session_id, title)
        record(
            conn, ctx, "session.created", workspace_id=input.ws, session_id=session_id, entity_type="session",
            entity_id=session_id, payload={"title": title},
        )  # fmt: skip
        return _wire(live(conn, input.ws, session_id))


def rename(ctx: RequestContext, input: RenameSessionInput) -> Session:
    title = require_text(input.title, "title")
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        row = live(conn, input.ws, input.session_id)
        repo.rename(conn, input.session_id, title)
        record(
            conn, ctx, "session.renamed", workspace_id=input.ws, session_id=input.session_id, entity_type="session",
            entity_id=input.session_id, payload={"old": row["title"], "new": title},
        )  # fmt: skip
        return _wire(live(conn, input.ws, input.session_id))


def delete(ctx: RequestContext, input: DeleteSessionInput) -> None:
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        live(conn, input.ws, input.session_id)
        if questions_repo.running_in_session(conn, input.session_id) is not None:
            raise ServiceError("conflict", "The session has a running question", {"session_id": input.session_id})
        repo.soft_delete(conn, input.session_id)
        record(
            conn, ctx, "session.deleted", workspace_id=input.ws, session_id=input.session_id, entity_type="session",
            entity_id=input.session_id,
        )  # fmt: skip


def messages(ctx: RequestContext, input: GetMessagesInput) -> builtins.list[ChatMsg]:
    with state.db() as conn:
        require(conn, input.ws)
        live(conn, input.ws, input.session_id)
        out: builtins.list[ChatMsg] = []
        for row in repo.messages(conn, input.ws, input.session_id):
            cited = [citations_repo.to_wire(conn, cid, n) for cid, n in repo.message_citations(conn, row["id"])]
            unverified = (
                [Unverified.model_validate(u) for u in json.loads(row["unverified"])] if row["unverified"] else None
            )
            out.append(
                ChatMsg(
                    id=row["id"], role=row["role"], text=row["text"],
                    citations=cited if row["role"] == "assistant" else None, unverified=unverified,
                )
            )  # fmt: skip
        return out
