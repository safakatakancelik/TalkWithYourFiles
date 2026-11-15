"""What every service function needs and does not receive as an argument: settings, a connection, the jobs.

Configured once by the server (and by the test fixtures). Each service call opens its own connection.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from twyf.config import Settings
from twyf.db.connection import connect as _connect
from twyf.files.jobs import InlineJobs, Jobs

if TYPE_CHECKING:  # both import this module
    from twyf.orchestration.engine import Engine
    from twyf.recording.context import RequestContext
    from twyf.services.questions import Tasks

_settings: Settings | None = None
_jobs: Jobs = InlineJobs()


def configure(settings: Settings, jobs: Jobs | None = None) -> None:
    global _settings, _jobs
    _settings = settings
    _jobs = jobs if jobs is not None else InlineJobs()


def jobs() -> Jobs:
    """Where ingestion runs: a worker thread in the server, inline in tests and seeding."""
    return _jobs


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


_engine: "Engine | None" = None
_tasks: "Tasks | None" = None


def configure_questions(engine: "Engine", tasks: "Tasks") -> None:
    """The running app's engine and its task registry."""
    global _engine, _tasks
    _engine, _tasks = engine, tasks


def engine() -> "Engine":
    if _engine is None:
        raise RuntimeError("no engine: the questions part of the app is not configured")
    return _engine


def tasks() -> "Tasks":
    if _tasks is None:
        raise RuntimeError("no task registry: the questions part of the app is not configured")
    return _tasks


def cancel_question(question_id: str, ctx: "RequestContext") -> None:
    """Asks the running engine to cancel a question, if this process runs one."""
    if _engine is None or _tasks is None:
        return
    _engine.cancel_context(question_id, ctx)
    _tasks.cancel(question_id)
