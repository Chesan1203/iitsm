from __future__ import annotations

import sqlite3
from dataclasses import replace

from app.domain.enums import IncidentStatus
from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.audit import AuditRecord
from app.persistence.codec import (
    day_start_text, dt_from_text, dt_to_text, enum_from_text, enum_to_text, next_day_start_text,
)
from app.persistence.database import Database
from app.ports.dto import AuditFilter
from app.ports.repositories import AuditRepository

SEARCH_LIMIT = 500


def _record(row: sqlite3.Row) -> AuditRecord:
    try:
        return AuditRecord(
            id=row["id"], incident_id=row["incident_id"], ticket_number=row["ticket_number"],
            timestamp=dt_from_text(row["timestamp"]), actor_id=row["actor_id"],
            actor_name=row["actor_name"], action=row["action"],
            previous_status=enum_from_text(IncidentStatus, row["previous_status"]),
            new_status=enum_from_text(IncidentStatus, row["new_status"]),
            description=row["description"])
    except InvalidInputError as exc:
        raise PersistenceError(f"Stored audit record {row['id']} is invalid: {exc}") from exc


class SqliteAuditRepository(AuditRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, record: AuditRecord) -> AuditRecord:
        """Audit records are append-only: always an insert. Returns a copy that has its id."""
        with self._db.connection() as conn:
            new_id = conn.execute(
                "INSERT INTO audit_records (incident_id, ticket_number, timestamp, actor_id, "
                "actor_name, action, previous_status, new_status, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.incident_id, record.ticket_number, dt_to_text(record.timestamp),
                 record.actor_id, record.actor_name, record.action,
                 enum_to_text(record.previous_status), enum_to_text(record.new_status),
                 record.description)).lastrowid
        return replace(record, id=new_id)

    def find_by_incident(self, incident_id: int) -> list[AuditRecord]:
        """One incident's history, oldest first (a timeline)."""
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM audit_records WHERE incident_id = ? "
                                "ORDER BY timestamp, id", (incident_id,)).fetchall()
        return [_record(r) for r in rows]

    def search(self, audit_filter: AuditFilter) -> list[AuditRecord]:
        """Newest first, at most 500 rows. Only the filters that are set apply."""
        clauses: list[str] = []
        params: list = []
        f = audit_filter
        if f.incident_id is not None:
            clauses.append("incident_id = ?")
            params.append(f.incident_id)
        if f.actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(f.actor_id)
        if f.action is not None:
            clauses.append("action = ?")
            params.append(f.action)
        if f.from_date is not None:
            clauses.append("timestamp >= ?")
            params.append(day_start_text(f.from_date))
        if f.to_date is not None:
            clauses.append("timestamp < ?")
            params.append(next_day_start_text(f.to_date))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db.connection() as conn:
            rows = conn.execute(f"SELECT * FROM audit_records{where} "
                                f"ORDER BY timestamp DESC, id DESC LIMIT {SEARCH_LIMIT}",
                                params).fetchall()
        return [_record(r) for r in rows]
