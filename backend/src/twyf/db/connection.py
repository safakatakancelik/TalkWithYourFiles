import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec


class Connection(sqlite3.Connection):
    """A connection that remembers whether the sqlite-vec extension loaded."""

    vec_loaded: bool = False


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, factory=Connection, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.vec_loaded = True
    except (AttributeError, sqlite3.Error):
        conn.vec_loaded = False
    return conn


def vec_loaded(conn: sqlite3.Connection) -> bool:
    return isinstance(conn, Connection) and conn.vec_loaded


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """One short write: BEGIN IMMEDIATE, then commit, or roll back on error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
