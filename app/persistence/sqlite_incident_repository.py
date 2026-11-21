from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from app.domain.enums import (
    EscalationLevel, IncidentStatus, NoteType, Priority, SlaStatus,
)
from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.snapshot import IncidentSnapshot
from app.persistence.codec import (
    day_start_text, dt_from_text, dt_to_text, enum_from_text, enum_to_text, flag,
    level_from_int, level_to_int, next_day_start_text, placeholders,
)
from app.persistence.database import Database
from app.persistence.sqlite_category_repository import categories_by_ids
from app.persistence.sqlite_service_repository import services_by_ids
from app.persistence.sqlite_user_repository import users_by_ids
from app.ports.dto import IncidentSearchCriteria
from app.ports.repositories import IncidentRepository

SEARCH_LIMIT = 500                        # safety cap on rows returned by one search

_ACTIVE = (IncidentStatus.ASSIGNED.name, IncidentStatus.ACKNOWLEDGED.name,
           IncidentStatus.IN_PROGRESS.name)
_RESOLVED = (IncidentStatus.RESOLVED.name, IncidentStatus.VERIFIED.name,
             IncidentStatus.CLOSED.name)

# Column names are fixed constants (never user input), so building SQL text from them is safe.
_COLUMNS = (
    "title", "description", "reporter_id", "category_id", "service_id", "impact", "urgency",
    "affected_users", "priority", "priority_score", "status", "created_at",
    "assigned_technician_id", "assigned_at", "acknowledged_at", "resolved_at", "verified_at",
    "closed_at", "escalation_level", "possible_duplicate_of",
    "sla_status", "sla_response_deadline", "sla_resolution_deadline", "sla_response_warned",
    "sla_resolution_warned", "sla_response_violated", "sla_resolution_violated",
    "resolution_summary", "resolution_details", "resolved_by_id", "resolution_at",
    "feedback_rating", "feedback_comment", "feedback_at",
)
_INSERT_SQL = (f"INSERT INTO incidents ({', '.join(_COLUMNS)}) "
               f"VALUES ({', '.join(':' + c for c in _COLUMNS)})")
_UPDATE_SQL = (f"UPDATE incidents SET {', '.join(f'{c} = :{c}' for c in _COLUMNS)} "
               f"WHERE id = :id")


def _params(incident: Incident) -> dict:
    """Flatten an incident into column values, reading it only through its snapshot."""
    s = incident.snapshot()
    tracker, resolution, feedback = s.sla_tracker, s.resolution, s.feedback
    return {
        "title": s.title, "description": s.description,
        "reporter_id": s.reporter.id, "category_id": s.category.id,
        "service_id": s.affected_service.id,
        "impact": level_to_int(s.impact), "urgency": level_to_int(s.urgency),
        "affected_users": s.affected_users,
        "priority": enum_to_text(s.priority), "priority_score": s.priority_score,
        "status": s.status.name, "created_at": dt_to_text(s.created_at),
        "assigned_technician_id": None if s.assigned_technician is None else s.assigned_technician.id,
        "assigned_at": dt_to_text(s.assigned_at), "acknowledged_at": dt_to_text(s.acknowledged_at),
        "resolved_at": dt_to_text(s.resolved_at), "verified_at": dt_to_text(s.verified_at),
        "closed_at": dt_to_text(s.closed_at), "escalation_level": s.escalation_level.name,
        "possible_duplicate_of": s.possible_duplicate_of,
        "sla_status": None if tracker is None else tracker.status.name,
        "sla_response_deadline": None if tracker is None else dt_to_text(tracker.response_deadline),
        "sla_resolution_deadline": None if tracker is None else dt_to_text(tracker.resolution_deadline),
        "sla_response_warned": 0 if tracker is None else flag(tracker.response_warned),
        "sla_resolution_warned": 0 if tracker is None else flag(tracker.resolution_warned),
        "sla_response_violated": 0 if tracker is None else flag(tracker.response_violated),
        "sla_resolution_violated": 0 if tracker is None else flag(tracker.resolution_violated),
        "resolution_summary": None if resolution is None else resolution.summary,
        "resolution_details": None if resolution is None else resolution.details,
        "resolved_by_id": None if resolution is None else resolution.resolved_by.id,
        "resolution_at": None if resolution is None else dt_to_text(resolution.resolved_at),
        "feedback_rating": None if feedback is None else feedback.rating,
        "feedback_comment": None if feedback is None else feedback.comment,
        "feedback_at": None if feedback is None else dt_to_text(feedback.submitted_at),
    }


class SqliteIncidentRepository(IncidentRepository):
    def __init__(self, db: Database):
        self._db = db

    # ---- save ---------------------------------------------------------------
    def save(self, incident: Incident) -> Incident:
        """Insert on first save (ticket number INC-<1000 + id>), otherwise update.
        The incident's notes are replaced as a set, in order, inside the same transaction."""
        params = _params(incident)
        identity = None
        with self._db.connection() as conn:
            if incident.id is None:
                incident_id = conn.execute(_INSERT_SQL, params).lastrowid
                ticket = f"INC-{1000 + incident_id}"
                conn.execute("UPDATE incidents SET ticket_number = ? WHERE id = ?",
                             (ticket, incident_id))
                identity = (incident_id, ticket)
            else:
                incident_id = incident.id
                if conn.execute(_UPDATE_SQL, {**params, "id": incident_id}).rowcount == 0:
                    raise PersistenceError(f"Incident {incident_id} does not exist")
            conn.execute("DELETE FROM incident_notes WHERE incident_id = ?", (incident_id,))
            conn.executemany(
                "INSERT INTO incident_notes (incident_id, author_id, note_type, text, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(incident_id, n.author.id, n.note_type.name, n.text, dt_to_text(n.created_at))
                 for n in incident.notes])
        if identity is not None:
            incident.assign_identity(*identity)   # only after the commit succeeded
        return incident

    # ---- single lookups -------------------------------------------------------
    def find_by_id(self, id: int) -> Incident | None:
        return self._first("SELECT * FROM incidents WHERE id = ?", (id,))

    def find_by_ticket(self, ticket_number: str) -> Incident | None:
        return self._first("SELECT * FROM incidents WHERE ticket_number = ?", (ticket_number,))

    # ---- lists ----------------------------------------------------------------
    def search(self, criteria: IncidentSearchCriteria) -> list[Incident]:
        """Only the criteria that are set narrow the result (all joined with AND).
        Values always travel as ? parameters, never inside the SQL text."""
        clauses: list[str] = []
        params: list = []
        c = criteria
        if c.ticket_number is not None:
            clauses.append("ticket_number = ?")
            params.append(c.ticket_number)
        if c.status is not None:
            clauses.append("status = ?")
            params.append(c.status.name)
        if c.priority is not None:
            clauses.append("priority = ?")
            params.append(c.priority.name)
        if c.category_id is not None:
            clauses.append("category_id = ?")
            params.append(c.category_id)
        if c.service_id is not None:
            clauses.append("service_id = ?")
            params.append(c.service_id)
        if c.technician_id is not None:
            clauses.append("assigned_technician_id = ?")
            params.append(c.technician_id)
        if c.reporter_id is not None:
            clauses.append("reporter_id = ?")
            params.append(c.reporter_id)
        if c.sla_status is not None:
            clauses.append("sla_status = ?")
            params.append(c.sla_status.name)
        if c.from_date is not None:
            clauses.append("created_at >= ?")
            params.append(day_start_text(c.from_date))
        if c.to_date is not None:
            clauses.append("created_at < ?")                  # whole end day is included
            params.append(next_day_start_text(c.to_date))
        if c.keyword is not None and c.keyword.strip():
            escaped = (c.keyword.strip().replace("\\", "\\\\")
                       .replace("%", "\\%").replace("_", "\\_"))
            clauses.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%"] * 2)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._list(f"SELECT * FROM incidents{where} "
                          f"ORDER BY created_at DESC, id DESC LIMIT {SEARCH_LIMIT}", params)

    def find_open(self) -> list[Incident]:
        return self._list("SELECT * FROM incidents WHERE status <> ? ORDER BY id",
                          (IncidentStatus.CLOSED.name,))

    def find_unacknowledged(self) -> list[Incident]:
        return self._list("SELECT * FROM incidents WHERE status = ? ORDER BY id",
                          (IncidentStatus.ASSIGNED.name,))

    def find_recent_by_service(self, service_id: int, since: datetime) -> list[Incident]:
        return self._list("SELECT * FROM incidents WHERE service_id = ? AND created_at >= ? "
                          "ORDER BY id", (service_id, dt_to_text(since)))

    def find_recent_by_reporter(self, reporter_id: int, since: datetime) -> list[Incident]:
        return self._list("SELECT * FROM incidents WHERE reporter_id = ? AND created_at >= ? "
                          "ORDER BY id", (reporter_id, dt_to_text(since)))

    # ---- counts ---------------------------------------------------------------
    def count_active_by_technician(self, technician_id: int) -> int:
        return self._count(
            f"SELECT COUNT(*) FROM incidents WHERE assigned_technician_id = ? "
            f"AND status IN ({placeholders(len(_ACTIVE))})", (technician_id, *_ACTIVE))

    def count_resolved_by_technician_on_service(self, technician_id: int, service_id: int) -> int:
        return self._count(
            f"SELECT COUNT(*) FROM incidents WHERE assigned_technician_id = ? AND service_id = ? "
            f"AND status IN ({placeholders(len(_RESOLVED))})", (technician_id, service_id, *_RESOLVED))

    # ---- helpers --------------------------------------------------------------
    def _count(self, sql: str, params: tuple) -> int:
        with self._db.connection() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def _first(self, sql: str, params) -> Incident | None:
        found = self._list(sql, params)
        return found[0] if found else None

    def _list(self, sql: str, params) -> list[Incident]:
        with self._db.connection() as conn:
            return self._load(conn, conn.execute(sql, params).fetchall())

    @staticmethod
    def _load(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Incident]:
        """Rebuild incidents from rows. Notes, users, services and categories are each loaded
        with ONE query for the whole list, then assembled (no query per incident)."""
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        note_rows = conn.execute(
            f"SELECT * FROM incident_notes WHERE incident_id IN ({placeholders(len(ids))}) "
            f"ORDER BY id", ids).fetchall()
        user_ids = {n["author_id"] for n in note_rows}
        for r in rows:
            user_ids.update((r["reporter_id"], r["assigned_technician_id"], r["resolved_by_id"]))
        users = users_by_ids(conn, user_ids)
        services = services_by_ids(conn, (r["service_id"] for r in rows))
        categories = categories_by_ids(conn, (r["category_id"] for r in rows))
        notes: dict[int, list[InvestigationNote]] = defaultdict(list)
        try:
            for n in note_rows:
                notes[n["incident_id"]].append(InvestigationNote(
                    id=n["id"], author=users[n["author_id"]],
                    note_type=enum_from_text(NoteType, n["note_type"]),
                    text=n["text"], created_at=dt_from_text(n["created_at"])))
            return [Incident.restore(_snapshot(r, users, services, categories, notes[r["id"]]))
                    for r in rows]
        except (KeyError, InvalidInputError) as exc:
            raise PersistenceError(f"Stored incident data is inconsistent: {exc!r}") from exc


def _snapshot(row: sqlite3.Row, users, services, categories, notes) -> IncidentSnapshot:
    technician = None if row["assigned_technician_id"] is None else users[row["assigned_technician_id"]]
    tracker = None
    if row["sla_response_deadline"] is not None:
        tracker = SlaTracker(
            dt_from_text(row["sla_response_deadline"]), dt_from_text(row["sla_resolution_deadline"]),
            bool(row["sla_response_warned"]), bool(row["sla_resolution_warned"]),
            bool(row["sla_response_violated"]), bool(row["sla_resolution_violated"]),
            enum_from_text(SlaStatus, row["sla_status"]))
    resolution = None
    if row["resolution_summary"] is not None:
        resolution = Resolution(row["resolution_summary"], row["resolution_details"] or "",
                                users[row["resolved_by_id"]], dt_from_text(row["resolution_at"]))
    feedback = None
    if row["feedback_rating"] is not None:
        feedback = Feedback(row["feedback_rating"], row["feedback_comment"] or "",
                            dt_from_text(row["feedback_at"]))
    return IncidentSnapshot(
        id=row["id"], ticket_number=row["ticket_number"], title=row["title"],
        description=row["description"], reporter=users[row["reporter_id"]],
        category=categories[row["category_id"]], affected_service=services[row["service_id"]],
        impact=level_from_int(row["impact"]), urgency=level_from_int(row["urgency"]),
        affected_users=row["affected_users"], priority=enum_from_text(Priority, row["priority"]),
        priority_score=row["priority_score"], status=enum_from_text(IncidentStatus, row["status"]),
        created_at=dt_from_text(row["created_at"]), assigned_technician=technician,
        assigned_at=dt_from_text(row["assigned_at"]),
        acknowledged_at=dt_from_text(row["acknowledged_at"]),
        resolved_at=dt_from_text(row["resolved_at"]), verified_at=dt_from_text(row["verified_at"]),
        closed_at=dt_from_text(row["closed_at"]),
        escalation_level=enum_from_text(EscalationLevel, row["escalation_level"]),
        possible_duplicate_of=row["possible_duplicate_of"], notes=tuple(notes),
        resolution=resolution, feedback=feedback, sla_tracker=tracker)
