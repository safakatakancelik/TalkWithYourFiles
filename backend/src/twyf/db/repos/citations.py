import sqlite3
from dataclasses import dataclass

from twyf.contract.models import Citation
from twyf.services.mapping import actor_to_wire


@dataclass(frozen=True)
class CitationRow:
    id: str
    workspace_id: str
    file_id: str
    file_version_id: str
    extraction_id: str
    char_start: int
    char_end: int
    quote: str
    passage_start: int
    passage_end: int
    passage: str
    location: str
    found_by_agent_id: str
    turn_id: str | None
    created_at: str


FIELDS = tuple(CitationRow.__dataclass_fields__)


def insert(conn: sqlite3.Connection, row: CitationRow) -> None:
    conn.execute(
        f"INSERT INTO citations ({', '.join(FIELDS)}) VALUES ({', '.join('?' for _ in FIELDS)})",
        [getattr(row, f) for f in FIELDS],
    )


def get(conn: sqlite3.Connection, citation_id: str) -> CitationRow | None:
    row = conn.execute("SELECT * FROM citations WHERE id = ?", (citation_id,)).fetchone()
    return CitationRow(**{f: row[f] for f in FIELDS}) if row is not None else None


def page(conn: sqlite3.Connection, citation: CitationRow) -> int | None:
    block = conn.execute(
        "SELECT page FROM blocks WHERE extraction_id = ? AND char_end > ? ORDER BY ordinal LIMIT 1",
        (citation.extraction_id, citation.char_start),
    ).fetchone()
    return block["page"] if block is not None else None


def to_wire(conn: sqlite3.Connection, citation_id: str, n: int) -> Citation:
    """The citation as the UI sees it, numbered `n`, with the name and number of the version it quotes."""
    citation = get(conn, citation_id)
    if citation is None:
        raise LookupError(f"no citation {citation_id}")
    version = conn.execute(
        "SELECT name, version FROM file_versions WHERE id = ?", (citation.file_version_id,)
    ).fetchone()
    found_page = page(conn, citation)
    return Citation(
        n=n,
        file_id=citation.file_id,
        agent_id=actor_to_wire(conn, citation.workspace_id, citation.found_by_agent_id),
        location=citation.location,
        passage=citation.passage,
        quote=citation.quote,
        id=citation.id,
        extraction_id=citation.extraction_id,
        start=citation.char_start,
        end=citation.char_end,
        page=found_page,
        file_name=version["name"],
        file_version=version["version"],
    )
