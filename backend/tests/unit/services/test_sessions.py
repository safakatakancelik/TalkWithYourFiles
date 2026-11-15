import sqlite3
import time

import pytest

from tests.conftest import EventsHelper, cite, upload
from twyf.contract.models import Unverified, Workspace
from twyf.contract.operations import (
    CreateSessionInput,
    DeleteFileInput,
    DeleteSessionInput,
    GetMessagesInput,
    ListSessionsInput,
    RenameSessionInput,
)
from twyf.db.connection import transaction
from twyf.recording.context import RequestContext
from twyf.services import agents, files, sessions
from twyf.services.errors import ServiceError


def test_sessions_latest_first(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    first = sessions.create(ctx, CreateSessionInput(ws=ws.id, title="First"))
    time.sleep(0.002)
    second = sessions.create(ctx, CreateSessionInput(ws=ws.id, title="Second"))
    assert [s.id for s in sessions.list(ctx, ListSessionsInput(ws=ws.id))] == [second.id, first.id]
    time.sleep(0.002)
    with transaction(conn):
        sessions.add_message(conn, ctx, workspace_id=ws.id, session_id=first.id, role="user", text="Hello")
    listed = sessions.list(ctx, ListSessionsInput(ws=ws.id))
    assert [s.id for s in listed] == [first.id, second.id]
    assert listed[0].message_count == 1


def test_rename_and_delete(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    s = sessions.create(ctx, CreateSessionInput(ws=ws.id, title="Old"))
    assert sessions.rename(ctx, RenameSessionInput(ws=ws.id, session_id=s.id, title="New")).title == "New"
    assert events("session.renamed")[0].payload == {"old": "Old", "new": "New"}
    sessions.delete(ctx, DeleteSessionInput(ws=ws.id, session_id=s.id))
    assert sessions.list(ctx, ListSessionsInput(ws=ws.id)) == []
    for call in (
        lambda: sessions.messages(ctx, GetMessagesInput(ws=ws.id, session_id=s.id)),
        lambda: sessions.rename(ctx, RenameSessionInput(ws=ws.id, session_id=s.id, title="x")),
    ):
        with pytest.raises(ServiceError) as raised:
            call()
        assert raised.value.code == "not_found"
    assert conn.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (s.id,)).fetchone()[0] == 1


def test_messages_with_citations(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper
) -> None:
    item = upload(ctx, ws.id, "lease.txt", b"The lease ends on 30 June 2029.")
    s = sessions.create(ctx, CreateSessionInput(ws=ws.id, title="Lease"))
    agent = agents.builtin(conn, ws.id, "chat").id
    cid = cite(conn, ctx, ws.id, item.id, "ends on 30 June 2029", agent)
    with transaction(conn):
        sessions.add_message(conn, ctx, workspace_id=ws.id, session_id=s.id, role="user", text="When?")
        sessions.add_message(
            conn, ctx.as_actor(agent), workspace_id=ws.id, session_id=s.id, role="assistant",
            text="It ends on 30 June 2029 [1].", citation_ids=[cid],
            unverified=[Unverified(text="Rent rises", reason="Not in the file")],
        )  # fmt: skip
    user, answer = sessions.messages(ctx, GetMessagesInput(ws=ws.id, session_id=s.id))
    assert (user.role, user.text, user.citations) == ("user", "When?", None)
    assert answer.citations is not None and [(c.n, c.id, c.file_name) for c in answer.citations] == [
        (1, cid, "lease.txt")
    ]
    assert answer.unverified == [Unverified(text="Rent rises", reason="Not in the file")]
    assert len(events("message.created")) == 2
    files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=item.id))
    [_, kept] = sessions.messages(ctx, GetMessagesInput(ws=ws.id, session_id=s.id))
    assert kept.citations is not None and kept.citations[0].file_name == "lease.txt"
