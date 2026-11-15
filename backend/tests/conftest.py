import io
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from twyf.agents.definitions import sync, sync_config
from twyf.config import Settings
from twyf.contract.models import EventRecord, FileItem, Workspace
from twyf.contract.operations import AddFileVersionInput, CreateWorkspaceInput, UploadFileInput
from twyf.db.connection import connect, transaction
from twyf.db.migrate import migrate
from twyf.db.repos import events as events_repo
from twyf.files.jobs import InlineJobs
from twyf.recording.context import RequestContext
from twyf.services import files, state, workspaces

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


SYSTEM = RequestContext(actor_id="system", source="internal", user_id="u_local", request_id="test")


@pytest.fixture
def synced(conn: sqlite3.Connection, settings: Settings) -> None:
    """The repository's .agents and the settings, snapshotted as the server does at start."""
    with transaction(conn):
        sync(conn, SYSTEM, settings)
        sync_config(conn, SYSTEM, settings)


@pytest.fixture
def ws(synced: None, ctx: RequestContext) -> Workspace:
    return workspaces.create(ctx, CreateWorkspaceInput(name="Test workspace"))


@pytest.fixture
def jobs(settings: Settings) -> InlineJobs:
    inline = InlineJobs()
    state.configure(settings, inline)
    return inline


def upload(ctx: RequestContext, ws_id: str, name: str, data: bytes, file_id: str | None = None) -> FileItem:
    return files.upload(ctx, UploadFileInput(ws=ws_id), name=name, stream=io.BytesIO(data), file_id=file_id)


def add_version(ctx: RequestContext, ws_id: str, file_id: str, name: str, data: bytes) -> FileItem:
    return files.add_version(ctx, AddFileVersionInput(ws=ws_id, file_id=file_id), name=name, stream=io.BytesIO(data))
