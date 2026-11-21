from __future__ import annotations

from app.persistence.database import Database
from app.ports.repositories import SettingsRepository


class SqliteSettingsRepository(SettingsRepository):
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        with self._db.connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else row["value"]

    def put(self, key: str, value: str) -> None:
        with self._db.connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
