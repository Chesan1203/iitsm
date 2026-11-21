from __future__ import annotations

import sqlite3
from dataclasses import replace

from app.domain.enums import SlaEventType
from app.domain.models.sla import SlaEvent
from app.persistence.codec import dt_from_text, dt_to_text, enum_from_text
from app.persistence.database import Database
from app.ports.repositories import SlaEventRepository


def _event(row: sqlite3.Row) -> SlaEvent:
    return SlaEvent(id=row["id"], incident_id=row["incident_id"],
                    event_type=enum_from_text(SlaEventType, row["event_type"]),
                    recorded_at=dt_from_text(row["recorded_at"]))


class SqliteSlaEventRepository(SlaEventRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, event: SlaEvent) -> SlaEvent:
        """Insert only. The same (incident, event type) pair can exist once: a second save
        raises PersistenceError, so check `exists` first when a repeat is possible."""
        with self._db.connection() as conn:
            new_id = conn.execute(
                "INSERT INTO sla_events (incident_id, event_type, recorded_at) VALUES (?, ?, ?)",
                (event.incident_id, event.event_type.name, dt_to_text(event.recorded_at))).lastrowid
        return replace(event, id=new_id)

    def find_by_incident(self, incident_id: int) -> list[SlaEvent]:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM sla_events WHERE incident_id = ? "
                                "ORDER BY recorded_at, id", (incident_id,)).fetchall()
        return [_event(r) for r in rows]

    def exists(self, incident_id: int, event_type: SlaEventType) -> bool:
        with self._db.connection() as conn:
            row = conn.execute("SELECT 1 FROM sla_events WHERE incident_id = ? AND event_type = ?",
                               (incident_id, event_type.name)).fetchone()
        return row is not None
