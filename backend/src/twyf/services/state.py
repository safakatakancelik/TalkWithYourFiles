"""What every service function needs and does not receive as an argument: the settings and a connection.

Configured once by the server (and by the test fixtures). Each service call opens its own connection.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from twyf.config import Settings
from twyf.db.connection import connect as _connect

_settings: Settings | None = None


def configure(settings: Settings) -> None:
    global _settings
    _settings = settings


def settings() -> Settings:
    if _settings is None:
        raise RuntimeError("twyf.services.state.configure() has not been called")
    return _settings


def db_path() -> Path:
    return settings().data_dir / "twyf.db"


def connect() -> sqlite3.Connection:
    """The connection factory: a new connection to the configured database."""
    return _connect(db_path())


@contextmanager
def db() -> Generator[sqlite3.Connection]:
    """A connection for one service call, closed afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
