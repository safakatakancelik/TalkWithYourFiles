import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from twyf.config import Settings
from twyf.contract.models import EventRecord
from twyf.db.connection import connect
from twyf.db.migrate import migrate
from twyf.db.repos import events as events_repo
from twyf.recording.context import RequestContext
from twyf.services import state

REPO_ROOT = Path(__file__).resolve().parents[2]

type EventsHelper = Callable[..., list[EventRecord]]


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Settings]:
    s = Settings(
        data_dir=tmp_path,
        runtime="fake",
        embedder="hash",
        parser="basic",
        first_read=False,
        agents_dir=REPO_ROOT / ".agents",
    )
    state.configure(s)
    yield s


@pytest.fixture
def db_path(settings: Settings) -> Path:
    return settings.data_dir / "twyf.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    migrate(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def ctx() -> RequestContext:
    return RequestContext(actor_id="u_local", source="api", user_id="u_local", request_id="test")


@pytest.fixture
def events(conn: sqlite3.Connection) -> EventsHelper:
    def read(type: str | None = None, **filters: Any) -> list[EventRecord]:
        return events_repo.list(conn, event_type=type, limit=100_000, **filters)

    return read
