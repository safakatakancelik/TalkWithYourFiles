"""Type 2 history for every `_versions` table: a new row per change, `valid_from`, `valid_to`."""

import sqlite3
from typing import Any

from twyf import clock


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def current(conn: sqlite3.Connection, table: str, key_col: str, key: str | int) -> sqlite3.Row | None:
    return conn.execute(f"SELECT * FROM {table} WHERE {key_col} = ? AND valid_to IS NULL", (key,)).fetchone()


def set_version(conn: sqlite3.Connection, table: str, key_col: str, key: str | int, values: dict[str, Any]) -> int:
    """Closes the current row of `key` and inserts the next one. Returns the new row's id.

    The closed row's `valid_to` equals the new row's `valid_from`, so the periods touch without overlap.
    """
    now = clock.now()
    conn.execute(f"UPDATE {table} SET valid_to = ? WHERE {key_col} = ? AND valid_to IS NULL", (now, key))
    row: dict[str, Any] = {key_col: key, **values, "valid_from": now, "valid_to": None}
    if "version" in _columns(conn, table) and "version" not in values:
        last = conn.execute(f"SELECT MAX(version) FROM {table} WHERE {key_col} = ?", (key,)).fetchone()[0]
        row["version"] = (last or 0) + 1
    names = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cursor = conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(row.values()))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def as_of(conn: sqlite3.Connection, table: str, key_col: str, key: str | int, at: str) -> sqlite3.Row | None:
    """The row of `key` in force at time `at`."""
    return conn.execute(
        f"SELECT * FROM {table} WHERE {key_col} = ? AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
        " ORDER BY id DESC LIMIT 1",
        (key, at, at),
    ).fetchone()
