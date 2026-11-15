"""Keyword search with SQLite FTS5 (BM25) over chunks of usable current versions."""

import re
import sqlite3

STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "so",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)
_TOKEN = re.compile(r"[^\W_]+")


def fts_query(text: str) -> str:
    """Tokens of at least 2 letters or digits, lower case, without stop words, each quoted, joined by OR."""
    tokens = [t for t in _TOKEN.findall(text.lower()) if len(t) >= 2 and t not in STOP_WORDS]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))


def search(
    conn: sqlite3.Connection, *, workspace_id: str, query: str, file_ids: list[str] | None, k: int
) -> list[tuple[int, float]]:
    """(chunk_id, score), best first. The score is the negated BM25, so higher is better."""
    match = fts_query(query)
    if not match:
        return []
    sql = (
        "SELECT c.id, -bm25(chunks_fts) AS score FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
        " JOIN extractions x ON x.id = c.extraction_id"
        " JOIN v_usable_files f ON f.file_version_id = x.file_version_id"
        " WHERE chunks_fts MATCH ? AND c.workspace_id = ?"
    )
    args: list[object] = [match, workspace_id]
    if file_ids is not None:
        sql += f" AND c.file_id IN ({', '.join('?' for _ in file_ids)})"
        args += file_ids
    sql += " ORDER BY bm25(chunks_fts), c.id LIMIT ?"
    args.append(k)
    return [(r[0], float(r[1])) for r in conn.execute(sql, args)]
