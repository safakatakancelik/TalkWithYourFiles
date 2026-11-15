"""How note weights act on what agents are given (05-retrieval-and-citations.md section 7)."""

import sqlite3
from collections.abc import Callable

import numpy as np

from twyf.contract.turns import NoteIn
from twyf.db.repos import embeddings
from twyf.retrieval import keyword
from twyf.retrieval.embedder import get_embedder
from twyf.retrieval.fusion import rrf
from twyf.services import state
from twyf.services.mapping import actor_name

MAX_NOTES = 20
MAX_CHARS = 6000
MAX_OTHER = 5
HIGH_BOOST = 1.25

_NOTES = (
    "SELECT n.id, n.file_id, n.file_version_id, n.file_version, n.author_id, n.kind, n.text, n.weight, n.created_at,"
    " f.name AS file_name, f.file_version_id AS current_version_id, w.rank, w.factor"
    " FROM v_notes n JOIN v_usable_files f ON f.id = n.file_id JOIN weights w ON w.code = n.weight"
    " JOIN notes raw ON raw.id = n.id"
    " WHERE n.workspace_id = ? AND n.weight != 'off'"
)


def _note_in(conn: sqlite3.Connection, row: sqlite3.Row) -> NoteIn:
    return NoteIn(
        note_id=row["id"],
        file_name=row["file_name"],
        author=actor_name(conn, row["author_id"]),
        kind=row["kind"],
        weight=row["weight"],
        text=row["text"],
        file_version=row["file_version"],
        earlier_version=row["file_version_id"] != row["current_version_id"],
    )


def notes_on_files(conn: sqlite3.Connection, *, workspace_id: str, file_ids: list[str]) -> list[NoteIn]:
    """Notes on these files: never `off`, never about an unusable file. High first, then newest, within budget."""
    if not file_ids:
        return []
    marks = ", ".join("?" for _ in file_ids)
    rows = conn.execute(
        _NOTES + f" AND n.file_id IN ({marks}) ORDER BY w.rank DESC, n.created_at DESC, raw.rowid DESC",
        [workspace_id, *file_ids],
    ).fetchall()
    chosen: list[NoteIn] = []
    chars = 0
    for row in rows:
        if len(chosen) == MAX_NOTES or chars + len(row["text"]) > MAX_CHARS:
            break
        chosen.append(_note_in(conn, row))
        chars += len(row["text"])
    return chosen


def _other_notes(conn: sqlite3.Connection, workspace_id: str, file_ids: list[str], query: str) -> list[NoteIn]:
    """Up to 5 notes from other files, by hybrid search over note text, ranked by fused score times weight factor."""
    exclude = f" AND n.file_id NOT IN ({', '.join('?' for _ in file_ids)})" if file_ids else ""
    base = [workspace_id, *file_ids]
    by_id = {r["id"]: r for r in conn.execute(_NOTES + exclude, base).fetchall()}
    if not by_id:
        return []
    lists: list[list[str]] = []
    match = keyword.fts_query(query)
    if match:
        hits = conn.execute(
            "SELECT note_id FROM notes_fts WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT 50", (match,)
        ).fetchall()
        lists.append([h[0] for h in hits if h[0] in by_id])
    embedder = get_embedder(state.settings())
    model = embeddings.find_model(conn, embedder) if embedder.dim else None
    if model is not None:
        rows = conn.execute(
            "SELECT note_id, vector FROM note_embeddings WHERE workspace_id = ? AND embedding_model_id = ?",
            (workspace_id, model),
        ).fetchall()
        rows = [r for r in rows if r["note_id"] in by_id]
        if rows:
            [vector] = embedder.embed([query])
            scores = np.stack([np.frombuffer(r["vector"], dtype="<f4") for r in rows]) @ np.asarray(vector, dtype="<f4")
            ranked = sorted(range(len(rows)), key=lambda i: -float(scores[i]))
            lists.append([rows[i]["note_id"] for i in ranked])
    fused = rrf(lists)
    weighted = sorted(((s * by_id[n]["factor"], n) for n, s in fused.items()), key=lambda t: (-t[0], t[1]))
    return [_note_in(conn, by_id[n]) for _, n in weighted[:MAX_OTHER]]


def notes_for_turn(conn: sqlite3.Connection, *, workspace_id: str, file_ids: list[str], query: str) -> list[NoteIn]:
    """The notes an agent's turn is given: those on its files, then up to 5 from other files."""
    own = notes_on_files(conn, workspace_id=workspace_id, file_ids=file_ids)
    seen = {n.note_id for n in own}
    return own + [n for n in _other_notes(conn, workspace_id, file_ids, query) if n.note_id not in seen]


def passage_boost(conn: sqlite3.Connection, workspace_id: str) -> Callable[[int], float]:
    """A chunk that overlaps a citation of a `high` note has its score multiplied by 1.25."""
    rows = conn.execute(
        "SELECT DISTINCT c.id FROM v_notes n JOIN note_citations nc ON nc.note_id = n.id"
        " JOIN citations ci ON ci.id = nc.citation_id"
        " JOIN chunks c ON c.extraction_id = ci.extraction_id AND c.char_start < ci.char_end AND c.char_end > ci.char_start"
        " WHERE n.workspace_id = ? AND n.weight = 'high'",
        (workspace_id,),
    ).fetchall()
    boosted = {r[0] for r in rows}
    return lambda chunk_id: HIGH_BOOST if chunk_id in boosted else 1.0
