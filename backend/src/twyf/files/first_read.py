"""The first read: one bounded translator turn on the opening of a newly indexed file (04-agents.md section 11)."""

import asyncio
import logging
import sqlite3
from collections.abc import Callable

from twyf.citations.locate import create_citation
from twyf.contextmap.service import add_mentions
from twyf.contract.turns import FirstReadInput, FirstReadOutput, PassageIn
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import files as files_repo
from twyf.db.repos import huddle
from twyf.files.integrity import verify
from twyf.orchestration import validators
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval.hybrid import count_chunks, first_chunks
from twyf.runtime.runner import TurnFailed, TurnRunner
from twyf.services.notes import create_agent_note

log = logging.getLogger(__name__)

type ConnFactory = Callable[[], sqlite3.Connection]


def reader(conn: sqlite3.Connection, workspace_id: str) -> str | None:
    """The generic translator with the fewest notes."""
    generic = [a for a in agents_repo.list(conn, workspace_id, "translator") if a.specialty == "generic"]
    if not generic:
        return None
    counts = {
        a.id: conn.execute("SELECT COUNT(*) FROM v_notes WHERE workspace_id = ? AND author_id = ?", (workspace_id, a.id)).fetchone()[0]
        for a in generic
    }  # fmt: skip
    return min(generic, key=lambda a: counts[a.id]).id


def _prepare(
    conn: sqlite3.Connection, ctx: RequestContext, file_id: str, chunks: int
) -> tuple[str, str, FirstReadInput] | None:
    row = conn.execute("SELECT workspace_id FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        return None
    ws = row["workspace_id"]
    current = files_repo.get(conn, ws, file_id)
    agent_id = reader(conn, ws)
    if current is None or agent_id is None or verify(conn, ctx, current["file_version_id"]) != "ok":
        return None
    passages = first_chunks(conn, workspace_id=ws, file_id=file_id, k=chunks)
    if not passages:
        return None
    with transaction(conn):
        huddle.assign(conn, workspace_id=ws, question_id=None, round_id=None, agent_id=agent_id, file_id=file_id,
                      file_version_id=current["file_version_id"], purpose="first_read")  # fmt: skip
        record(conn, ctx.as_actor(agent_id), "huddle.file_assigned", workspace_id=ws, entity_type="file", entity_id=file_id,
               payload={"agent_id": agent_id, "purpose": "first_read"})  # fmt: skip
    first_input = FirstReadInput(
        file_name=current["name"],
        passages=[
            PassageIn(
                passage_id=p.passage_id, file_id=p.file_id, file_name=p.file_name, location=p.location, text=p.text
            )
            for p in passages
        ],
        chunks_shown=len(passages),
        chunks_total=count_chunks(conn, workspace_id=ws, file_id=file_id),
    )
    return ws, agent_id, first_input


async def first_read(runner: TurnRunner, conn_factory: ConnFactory, ctx: RequestContext, file_id: str) -> None:
    """Exactly one turn, given the first `first_read_chunks` chunks. No search, no second turn."""

    def with_conn[T](fn: Callable[[sqlite3.Connection], T]) -> T:
        conn = conn_factory()
        try:
            return fn(conn)
        finally:
            conn.close()

    prepared = await asyncio.to_thread(
        with_conn, lambda c: _prepare(c, ctx, file_id, runner.settings.first_read_chunks)
    )
    if prepared is None:
        return
    ws, agent_id, first_input = prepared
    passages = {p.passage_id: p.file_id for p in first_input.passages}
    agent_ctx = ctx.as_actor(agent_id)

    def rules(out: FirstReadOutput) -> list[str]:
        def run(conn: sqlite3.Connection) -> list[str]:
            check = validators.passage_quote_check(conn, agent_ctx, ws, passages)
            return validators.unknown_ids(out, first_input) + validators.first_read(out, check)

        return with_conn(run)

    try:
        out, turn_id = await runner.run(agent_ctx, agent_id=agent_id, turn_type="first_read", input=first_input,
                                        output_model=FirstReadOutput, validate=rules)  # fmt: skip
    except TurnFailed as failed:
        log.warning("the first read of %s failed: %s", file_id, failed.reason)
        return

    def store(conn: sqlite3.Connection) -> None:
        with transaction(conn):
            cited = [
                create_citation(conn, agent_ctx, workspace_id=ws, passage_id=q.passage_id or "", quote=q.quote or "",
                                agent_id=agent_id, turn_id=turn_id).id
                for q in out.summary.quotes
            ]  # fmt: skip
            create_agent_note(conn, agent_ctx, workspace_id=ws, file_id=file_id, author_id=agent_id, kind=out.summary.kind,
                              text=out.summary.text, citation_ids=list(dict.fromkeys(cited)), numbers=[],
                              question_id=None, turn_id=turn_id)  # fmt: skip
            add_mentions(conn, agent_ctx, workspace_id=ws, entities=out.entities, passage_file=lambda p: passages[p],
                         question_id=None)  # fmt: skip

    await asyncio.to_thread(with_conn, store)
