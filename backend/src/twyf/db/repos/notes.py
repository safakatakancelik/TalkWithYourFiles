import builtins
import sqlite3
from dataclasses import dataclass

from twyf import clock
from twyf.db.repos import versioned
from twyf.db.repos.embeddings import pack


@dataclass(frozen=True)
class NoteRow:
    id: str
    workspace_id: str
    file_id: str
    file_version_id: str
    author_id: str
    kind: str
    question_id: str | None
    turn_id: str | None
    created_at: str


def insert(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    workspace_id: str,
    file_id: str,
    file_version_id: str,
    author_id: str,
    kind: str,
    text: str,
    citation_ids: builtins.list[str],
    question_id: str | None,
    turn_id: str | None,
) -> NoteRow:
    """The note, its text as version 1, weight normal, and its citations numbered from 1."""
    row = NoteRow(note_id, workspace_id, file_id, file_version_id, author_id, kind, question_id, turn_id, clock.now())
    conn.execute(
        "INSERT INTO notes (id, workspace_id, file_id, file_version_id, author_id, kind, question_id, turn_id,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row.id, workspace_id, file_id, file_version_id, author_id, kind, question_id, turn_id, row.created_at),
    )
    versioned.set_version(conn, "note_versions", "note_id", note_id, {"text": text})
    versioned.set_version(conn, "note_weights", "note_id", note_id, {"weight": "normal", "set_by": author_id})
    conn.executemany(
        "INSERT INTO note_citations (note_id, citation_id, n) VALUES (?, ?, ?)",
        [(note_id, cid, n) for n, cid in enumerate(citation_ids, start=1)],
    )
    set_search_text(conn, note_id, text)
    return row


def set_search_text(conn: sqlite3.Connection, note_id: str, text: str) -> None:
    """Replaces the note's row in the notes_fts cache."""
    conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
    conn.execute("INSERT INTO notes_fts (note_id, text) VALUES (?, ?)", (note_id, text))


def set_vector(
    conn: sqlite3.Connection, note_id: str, model: int, workspace_id: str, vector: builtins.list[float]
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO note_embeddings (note_id, embedding_model_id, workspace_id, vector) VALUES (?, ?, ?, ?)",
        (note_id, model, workspace_id, pack(vector)),
    )


def get(conn: sqlite3.Connection, workspace_id: str, note_id: str) -> sqlite3.Row | None:
    """A live note of this workspace, on a live file, or None."""
    return conn.execute("SELECT * FROM v_notes WHERE workspace_id = ? AND id = ?", (workspace_id, note_id)).fetchone()


def list(conn: sqlite3.Connection, workspace_id: str) -> builtins.list[sqlite3.Row]:
    return conn.execute(
        "SELECT v.* FROM v_notes v JOIN notes n ON n.id = v.id WHERE v.workspace_id = ? ORDER BY v.created_at, n.rowid",
        (workspace_id,),
    ).fetchall()


def citation_ids(conn: sqlite3.Connection, note_id: str) -> builtins.list[str]:
    return [
        r[0] for r in conn.execute("SELECT citation_id FROM note_citations WHERE note_id = ? ORDER BY n", (note_id,))
    ]


def set_text(conn: sqlite3.Connection, note_id: str, text: str) -> None:
    versioned.set_version(conn, "note_versions", "note_id", note_id, {"text": text})
    set_search_text(conn, note_id, text)


def set_weight(conn: sqlite3.Connection, note_id: str, weight: str, set_by: str) -> None:
    versioned.set_version(conn, "note_weights", "note_id", note_id, {"weight": weight, "set_by": set_by})


def soft_delete(conn: sqlite3.Connection, note_id: str) -> None:
    conn.execute("UPDATE notes SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (clock.now(), note_id))


def without_vectors(conn: sqlite3.Connection, model: int) -> builtins.list[sqlite3.Row]:
    """Live notes on live files that have no vector for this model."""
    return conn.execute(
        "SELECT v.id, v.workspace_id, v.text FROM v_notes v WHERE NOT EXISTS"
        " (SELECT 1 FROM note_embeddings e WHERE e.note_id = v.id AND e.embedding_model_id = ?) ORDER BY v.created_at",
        (model,),
    ).fetchall()
