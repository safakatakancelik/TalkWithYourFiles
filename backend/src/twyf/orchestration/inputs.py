"""Builds the parts of each turn's input from the database. Only usable files and their notes appear."""

import sqlite3
from pathlib import PurePath

from twyf.contract.turns import AgentInfo, CitationIn, FileInfo, HistoryItem
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import citations as citations_repo
from twyf.db.repos import files as files_repo
from twyf.retrieval.weights import notes_on_files

HISTORY = 6


def usable_ready_files(conn: sqlite3.Connection, workspace_id: str) -> list[sqlite3.Row]:
    """Live files whose copy passes the availability check and whose current version is indexed."""
    rows = conn.execute(
        "SELECT f.* FROM v_usable_files f JOIN files raw ON raw.id = f.id WHERE f.workspace_id = ?"
        " ORDER BY f.created_at, raw.rowid",
        (workspace_id,),
    ).fetchall()
    return [r for r in rows if files_repo.status(conn, r["file_version_id"], r["availability"]) == "ready"]


def file_infos(conn: sqlite3.Connection, workspace_id: str, rows: list[sqlite3.Row]) -> list[FileInfo]:
    return [
        FileInfo(
            file_id=r["id"], name=r["name"], type=r["file_type"],
            notes=notes_on_files(conn, workspace_id=workspace_id, file_ids=[r["id"]]),
        )
        for r in rows
    ]  # fmt: skip


def agent_infos(conn: sqlite3.Connection, workspace_id: str, usable_file_ids: set[str]) -> list[AgentInfo]:
    out: list[AgentInfo] = []
    for agent in agents_repo.list(conn, workspace_id, "translator"):
        rows = conn.execute(
            "SELECT file_id FROM v_notes WHERE workspace_id = ? AND author_id = ? ORDER BY created_at",
            (workspace_id, agent.id),
        ).fetchall()
        worked = list(dict.fromkeys(r[0] for r in rows if r[0] in usable_file_ids))
        out.append(
            AgentInfo(
                agent_id=agent.id, name=agent.name, specialty=agent.specialty, note_count=len(rows), files_worked=worked
            )
        )
    return out


def history(conn: sqlite3.Connection, session_id: str, before_question: str) -> list[HistoryItem]:
    """The last messages of the session before this question's own user message."""
    rows = conn.execute(
        "SELECT role, text, question_id FROM messages WHERE session_id = ? ORDER BY created_at, rowid", (session_id,)
    ).fetchall()
    earlier = [r for r in rows if r["question_id"] != before_question]
    return [HistoryItem(role=r["role"], text=r["text"]) for r in earlier[-HISTORY:]]


def citation_in(conn: sqlite3.Connection, citation_id: str, n: int) -> CitationIn:
    row = citations_repo.get(conn, citation_id)
    assert row is not None
    name = conn.execute("SELECT name FROM file_versions WHERE id = ?", (row.file_version_id,)).fetchone()[0]
    return CitationIn(
        citation_id=row.id, n=n, file_name=name, location=row.location, passage=row.passage, quote=row.quote
    )


def named(conn: sqlite3.Connection, workspace_id: str, question: str) -> tuple[list[str], list[str]]:
    """Files named by their name without extension, and translators by name, case-insensitive, in the question."""
    text = question.lower()
    files = conn.execute(
        "SELECT f.id, f.name FROM v_files f JOIN files raw ON raw.id = f.id WHERE f.workspace_id = ? ORDER BY raw.rowid",
        (workspace_id,),
    ).fetchall()
    file_ids = [f["id"] for f in files if (stem := PurePath(f["name"]).stem.lower().strip()) and stem in text]
    agent_ids = [a.id for a in agents_repo.list(conn, workspace_id, "translator") if a.name.lower() in text]
    return file_ids, agent_ids
