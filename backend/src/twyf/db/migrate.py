"""Applies db/migrations/NNNN_name.sql in order, each in one transaction. Forward only."""

import re
import sqlite3
from pathlib import Path

from twyf import clock
from twyf.db.connection import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{4})_(\w+)\.sql$")


def _available() -> list[tuple[int, str, Path]]:
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        match = _NAME.match(path.name)
        if match:
            found.append((int(match.group(1)), match.group(2), path))
    return found


def _applied(conn: sqlite3.Connection) -> set[int]:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if exists is None:
        return set()
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def _back_up(conn: sqlite3.Connection, path: Path, version: int) -> None:
    target = sqlite3.connect(path.with_name(f"{path.name}.bak-{version:04d}"))
    try:
        conn.backup(target)
    finally:
        target.close()


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def migrate(path: Path) -> list[int]:
    """Applies every migration not yet applied to the database at `path`. Returns the versions applied."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        done = _applied(conn)
        pending = [m for m in _available() if m[0] not in done]
        applied: list[int] = []
        for version, name, file in pending:
            if done:
                _back_up(conn, path, version)
            now = _quote(clock.now())
            script = file.read_text().replace(":now", now)
            record = f"INSERT INTO schema_migrations VALUES ({version}, {_quote(name)}, {now});"
            try:
                conn.executescript(f"BEGIN IMMEDIATE;\n{script}\n{record}\nCOMMIT;")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            applied.append(version)
        return applied
    finally:
        conn.close()
