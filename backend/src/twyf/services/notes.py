import builtins
import sqlite3

from twyf.contract.events import NoteEvent
from twyf.contract.models import Note
from twyf.contract.operations import AddNoteInput, DeleteNoteInput, EditNoteInput, ListNotesInput, SetNoteWeightInput
from twyf.db.connection import transaction
from twyf.db.repos import citations as citations_repo
from twyf.db.repos import embeddings
from twyf.db.repos import files as files_repo
from twyf.db.repos import notes as repo
from twyf.db.repos.notes import NoteRow
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.retrieval.embedder import get_embedder
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.mapping import actor_name, actor_to_wire
from twyf.services.workspaces import require

EVIDENCE_KINDS = ("summary", "finding")


def note_to_wire(conn: sqlite3.Connection, row: sqlite3.Row, numbers: list[int] | None = None) -> Note:
    """A v_notes row on the wire. Citations are numbered from 1 unless `numbers` gives the question's numbering."""
    ids = repo.citation_ids(conn, row["id"])
    marks = numbers if numbers is not None else builtins.list(range(1, len(ids) + 1))
    return Note(
        id=row["id"],
        file_id=row["file_id"],
        author_id=actor_to_wire(conn, row["workspace_id"], row["author_id"]),
        kind=row["kind"],
        text=row["text"],
        citations=[citations_repo.to_wire(conn, cid, n) for cid, n in zip(ids, marks, strict=True)],
        created_at=row["created_at"],
        weight=row["weight"],
        author_name=actor_name(conn, row["author_id"]),
        file_version=row["file_version"],
    )


def _embed(conn: sqlite3.Connection, note_id: str, workspace_id: str, text: str) -> None:
    embedder = get_embedder(state.settings())
    if embedder.dim == 0:
        return
    [vector] = embedder.embed([text])
    repo.set_vector(conn, note_id, embeddings.model_id(conn, embedder), workspace_id, vector)


def _live_note(conn: sqlite3.Connection, ws_id: str, note_id: str) -> sqlite3.Row:
    row = repo.get(conn, ws_id, note_id)
    if row is None:
        raise ServiceError("not_found", "No such note", {"note_id": note_id})
    return row


def _is_user(conn: sqlite3.Connection, actor_id: str) -> bool:
    row = conn.execute("SELECT actor_kind FROM actors WHERE id = ?", (actor_id,)).fetchone()
    return row is not None and row["actor_kind"] == "user"


def create_agent_note(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    *,
    workspace_id: str,
    file_id: str,
    author_id: str,
    kind: str,
    text: str,
    citation_ids: list[str],
    numbers: list[int],
    question_id: str | None,
    turn_id: str | None,
) -> NoteRow:
    """A note written by an agent, inside the caller's transaction. A summary or finding needs at least one
    citation, and every citation points into the note's own file. Inside a question the `note` event carries the
    question's citation numbers."""
    if kind in EVIDENCE_KINDS and not citation_ids:
        raise ServiceError("validation", f"A {kind} note needs at least one citation")
    for cid in citation_ids:
        citation = citations_repo.get(conn, cid)
        if citation is None or citation.file_id != file_id or citation.workspace_id != workspace_id:
            raise ServiceError(
                "validation", "Every citation of a note must point into the note's own file", {"citation_id": cid}
            )
    current = files_repo.get(conn, workspace_id, file_id)
    if current is None:
        raise ServiceError("not_found", "No such file", {"file_id": file_id})
    row = repo.insert(
        conn, note_id=new_id("n"), workspace_id=workspace_id, file_id=file_id,
        file_version_id=current["file_version_id"], author_id=author_id, kind=kind, text=text,
        citation_ids=citation_ids, question_id=question_id, turn_id=turn_id,
    )  # fmt: skip
    _embed(conn, row.id, workspace_id, text)
    stored = repo.get(conn, workspace_id, row.id)
    assert stored is not None
    wire = NoteEvent(note=note_to_wire(conn, stored, numbers or None)) if question_id is not None else None
    record(
        conn, ctx, "note.created", workspace_id=workspace_id, question_id=question_id, turn_id=turn_id,
        entity_type="note", entity_id=row.id, payload={"file_id": file_id, "kind": kind}, wire=wire,
    )  # fmt: skip
    return row


def list(ctx: RequestContext, input: ListNotesInput) -> list[Note]:
    with state.db() as conn:
        require(conn, input.ws)
        return [note_to_wire(conn, row) for row in repo.list(conn, input.ws)]


def add(ctx: RequestContext, input: AddNoteInput) -> Note:
    """A note written by the user: always an interpretation, with no citations."""
    text = require_text(input.text, "text")
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        current = files_repo.get(conn, input.ws, input.file_id)
        if current is None:
            raise ServiceError("not_found", "No such file", {"file_id": input.file_id})
        row = repo.insert(
            conn, note_id=new_id("n"), workspace_id=input.ws, file_id=input.file_id,
            file_version_id=current["file_version_id"], author_id=ctx.actor_id, kind="interpretation", text=text,
            citation_ids=[], question_id=None, turn_id=None,
        )  # fmt: skip
        _embed(conn, row.id, input.ws, text)
        record(
            conn, ctx, "note.created", workspace_id=input.ws, entity_type="note", entity_id=row.id,
            payload={"file_id": input.file_id, "kind": "interpretation"},
        )  # fmt: skip
        return note_to_wire(conn, _live_note(conn, input.ws, row.id))


def edit(ctx: RequestContext, input: EditNoteInput) -> Note:
    """Only a note written by the user. An agent's note is tied to its citations."""
    text = require_text(input.text, "text")
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        row = _live_note(conn, input.ws, input.note_id)
        if not _is_user(conn, row["author_id"]):
            raise ServiceError(
                "validation", "Only a note written by the user can be edited", {"note_id": input.note_id}
            )
        repo.set_text(conn, input.note_id, text)
        _embed(conn, input.note_id, input.ws, text)
        record(
            conn, ctx, "note.edited", workspace_id=input.ws, entity_type="note", entity_id=input.note_id,
            payload={"old": row["text"], "new": text},
        )  # fmt: skip
        return note_to_wire(conn, _live_note(conn, input.ws, input.note_id))


def delete(ctx: RequestContext, input: DeleteNoteInput) -> None:
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        _live_note(conn, input.ws, input.note_id)
        repo.soft_delete(conn, input.note_id)
        record(conn, ctx, "note.deleted", workspace_id=input.ws, entity_type="note", entity_id=input.note_id)


def set_weight(ctx: RequestContext, input: SetNoteWeightInput) -> None:
    """One `note.weight_set` per note whose weight changes. Acts on later turns only."""
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        rows = [_live_note(conn, input.ws, note_id) for note_id in dict.fromkeys(input.note_ids)]
        for row in rows:
            if row["weight"] == input.weight:
                continue
            repo.set_weight(conn, row["id"], input.weight, ctx.actor_id)
            record(
                conn, ctx, "note.weight_set", workspace_id=input.ws, entity_type="note", entity_id=row["id"],
                payload={"old": row["weight"], "new": input.weight},
            )  # fmt: skip
