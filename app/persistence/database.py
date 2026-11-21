"""The only place that opens SQLite connections.

Every repository receives a `Database` and calls `with db.connection() as conn:` for each
operation. A short-lived connection per operation keeps the web server and the background
scheduler (different threads) from ever sharing one connection.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.domain.exceptions import PersistenceError

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")
_MEMORY_NAMES = {":memory:", ""}


class Database:
    """Opens connections to one SQLite file and creates its tables."""

    def __init__(self, path: str | Path):
        text = str(path).strip()
        if text in _MEMORY_NAMES:
            # Every new connection to ":memory:" is a separate, empty database, so tables
            # created by initialise() would vanish. Refuse instead of failing confusingly later.
            raise PersistenceError(
                "In-memory databases are not supported (each connection would get its own "
                "empty database). Use a file path, for example a temporary file in tests.")
        self._path = Path(text)

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for one unit of work.

        Commits when the block ends normally, rolls back when it raises, and always closes.
        Any sqlite3.Error becomes PersistenceError so raw database errors never leave this
        folder; our own exceptions (for example NotFoundError) pass through untouched.
        """
        conn = None
        try:
            conn = sqlite3.connect(self._path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")      # off by default in SQLite
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            self._rollback(conn)
            raise PersistenceError(f"Database operation failed: {exc}") from exc
        except BaseException:
            self._rollback(conn)
            raise
        finally:
            if conn is not None:
                conn.close()

    def initialise(self) -> None:
        """Create the parent folder and every table. Safe to call any number of times."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            schema = _SCHEMA_FILE.read_text(encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(f"Cannot prepare database at {self._path}: {exc}") from exc
        with self.connection() as conn:
            # WAL lets the scheduler write while the web server reads. The setting is stored
            # in the database file, so it only needs to be switched on here.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(schema)

    @staticmethod
    def _rollback(conn: sqlite3.Connection | None) -> None:
        if conn is None:
            return
        try:
            conn.rollback()
        except sqlite3.Error:
            pass                                          # the original error matters more
