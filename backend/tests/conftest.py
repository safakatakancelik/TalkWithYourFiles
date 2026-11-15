import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from twyf.db.connection import connect
from twyf.db.migrate import migrate


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "twyf.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    migrate(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()
