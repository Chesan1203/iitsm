from __future__ import annotations

from app.domain.enums import IncidentStatus, Priority, Role, SlaEventType
from app.persistence.codec import dt_from_text, enum_from_text
from app.persistence.database import Database
from app.ports.dto import CountRow, OverviewReport, SlaViolationRow, WorkloadRow
from app.ports.repositories import ReportRepository

# Fixed constants only; every status list is turned into ? placeholders, never joined as text.
_RESOLVED = (IncidentStatus.RESOLVED.name, IncidentStatus.VERIFIED.name, IncidentStatus.CLOSED.name)
_ACTIVE = (IncidentStatus.ASSIGNED.name, IncidentStatus.ACKNOWLEDGED.name,
           IncidentStatus.IN_PROGRESS.name)
_VIOLATIONS = (SlaEventType.RESPONSE_VIOLATED.name, SlaEventType.RESOLUTION_VIOLATED.name)


def _marks(values: tuple) -> str:
    return ", ".join("?" * len(values))


class SqliteReportRepository(ReportRepository):
    """Read-only queries for the administrator dashboards. Nothing here changes data."""

    def __init__(self, db: Database):
        self._db = db

    def get_overview(self) -> OverviewReport:
        """open = not RESOLVED/VERIFIED/CLOSED; critical_open = open and P1;
        resolved = RESOLVED/VERIFIED/CLOSED; sla_violations = distinct incidents that have a
        violation event."""
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS total, "
                f"COALESCE(SUM(status NOT IN ({_marks(_RESOLVED)})), 0) AS open, "
                f"COALESCE(SUM(status NOT IN ({_marks(_RESOLVED)}) AND priority = ?), 0) AS critical_open, "
                f"COALESCE(SUM(status IN ({_marks(_RESOLVED)})), 0) AS resolved "
                f"FROM incidents",
                (*_RESOLVED, *_RESOLVED, Priority.P1.name, *_RESOLVED)).fetchone()
            violations = conn.execute(
                f"SELECT COUNT(DISTINCT incident_id) FROM sla_events "
                f"WHERE event_type IN ({_marks(_VIOLATIONS)})", _VIOLATIONS).fetchone()[0]
        return OverviewReport(total=row["total"], open=row["open"],
                              critical_open=row["critical_open"], resolved=row["resolved"],
                              sla_violations=violations)

    def get_technician_workload(self) -> list[WorkloadRow]:
        """Every technician, including those with zero active incidents (LEFT JOIN)."""
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT u.id, u.full_name, u.max_workload, COUNT(i.id) AS active_count "
                f"FROM users u LEFT JOIN incidents i "
                f"ON i.assigned_technician_id = u.id AND i.status IN ({_marks(_ACTIVE)}) "
                f"WHERE u.role = ? GROUP BY u.id ORDER BY active_count DESC, u.full_name, u.id",
                (*_ACTIVE, Role.TECHNICIAN.name)).fetchall()
        return [WorkloadRow(technician_id=r["id"], technician_name=r["full_name"],
                            active_count=r["active_count"], max_workload=r["max_workload"])
                for r in rows]

    def get_service_analysis(self) -> list[CountRow]:
        return self._counts("it_services", "service_id")

    def get_category_analysis(self) -> list[CountRow]:
        return self._counts("categories", "category_id")

    def get_sla_violations(self) -> list[SlaViolationRow]:
        """Violation events with their incident and technician, newest first."""
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT i.ticket_number, i.title, i.priority, t.full_name AS technician_name, "
                f"e.event_type, e.recorded_at "
                f"FROM sla_events e JOIN incidents i ON i.id = e.incident_id "
                f"LEFT JOIN users t ON t.id = i.assigned_technician_id "
                f"WHERE e.event_type IN ({_marks(_VIOLATIONS)}) "
                f"ORDER BY e.recorded_at DESC, e.id DESC", _VIOLATIONS).fetchall()
        return [SlaViolationRow(
            ticket_number=r["ticket_number"], title=r["title"],
            priority=enum_from_text(Priority, r["priority"]),
            technician_name=r["technician_name"],
            event_type=enum_from_text(SlaEventType, r["event_type"]),
            recorded_at=dt_from_text(r["recorded_at"])) for r in rows]

    def _counts(self, table: str, column: str) -> list[CountRow]:
        """Incidents per service or category, largest first. `table` and `column` come from
        the two fixed calls above, never from user input."""
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT x.name, COUNT(i.id) AS n FROM {table} x "
                f"LEFT JOIN incidents i ON i.{column} = x.id "
                f"GROUP BY x.id ORDER BY n DESC, x.name").fetchall()
        return [CountRow(label=r["name"], count=r["n"]) for r in rows]
