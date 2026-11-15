import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlite_vec


class Connection(sqlite3.Connection):
    """A connection that remembers whether sqlite-vec loaded, and what to do once its transaction commits."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.vec_loaded = False
        self.on_commit: list[Callable[[], None]] = []


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


def after_commit(conn: sqlite3.Connection, fn: Callable[[], None]) -> None:
    """Runs `fn` when the current transaction commits, never on rollback. Outside a transaction it runs now."""
    if isinstance(conn, Connection) and conn.in_transaction:
        conn.on_commit.append(fn)
    else:
        fn()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """One short write: BEGIN IMMEDIATE, then commit, or roll back on error."""
    hooks = conn.on_commit if isinstance(conn, Connection) else []
    hooks.clear()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        hooks.clear()
        raise
    conn.execute("COMMIT")
    pending = list(hooks)
    hooks.clear()
    for fn in pending:
        fn()
