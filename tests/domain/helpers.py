from datetime import datetime, timedelta

from app.domain.enums import AdminLevel, IncidentStatus, Level, Priority
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Administrator, Employee, Technician
from app.domain.strategies.priority import PriorityResult

T0 = datetime(2026, 11, 14, 10, 5)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def make_employee(id: int = 1, username: str = "emp1") -> Employee:
    return Employee(username, "Asha Rao", f"{username}@x.com", "hash", "Finance", id=id)


def make_technician(id: int = 2, username: str = "tech1", available: bool = True,
                    max_workload: int = 5, active: bool = True) -> Technician:
    return Technician(username, "Ravi K", f"{username}@x.com", "hash", {"Database"}, 4,
                      available, max_workload, id=id, active=active)


def make_admin(id: int = 10) -> Administrator:
    return Administrator("admin1", "Meera N", "admin1@x.com", "hash", AdminLevel.TEAM_LEAD, id=id)


def _category() -> Category:
    return Category("Database", "DB issues", "Database", id=1)


def _service() -> ITService:
    return ITService("Payment", "Payments", Level.HIGH, id=1)


def make_priority_result(priority: Priority = Priority.P1, score: int = 27) -> PriorityResult:
    return PriorityResult(score, priority, "3x3x3 = 27")


def make_tracker(start: datetime = T0) -> SlaTracker:
    return SlaTracker(start + timedelta(minutes=5), start + timedelta(minutes=30))


def make_incident() -> Incident:
    """A brand-new incident in status NEW, reported by employee id 1."""
    return Incident("Payment down", "Cannot pay", make_employee(), _category(), _service(),
                    Level.HIGH, Level.HIGH, 120, T0)


def make_incident_in(status: IncidentStatus) -> Incident:
    """An incident restored directly into `status`, with the fields that status implies."""
    idx = list(IncidentStatus).index(status)
    tech = make_technician()
    snapshot = IncidentSnapshot(
        id=100 + idx, ticket_number=f"INC-{1100 + idx}", title="Payment down",
        description="Cannot pay", reporter=make_employee(), category=_category(),
        affected_service=_service(), impact=Level.HIGH, urgency=Level.HIGH, affected_users=120,
        priority=Priority.P1 if idx >= 1 else None, priority_score=27 if idx >= 1 else None,
        status=status, created_at=T0,
        assigned_technician=tech if idx >= 2 else None, assigned_at=at(2) if idx >= 2 else None,
        acknowledged_at=at(3) if idx >= 3 else None,
        resolved_at=at(6) if idx >= 5 else None,
        verified_at=at(7) if idx >= 6 else None,
        closed_at=at(8) if idx >= 7 else None,
        resolution=Resolution("Restarted DB pool", "Pool was exhausted", tech, at(6)) if idx >= 5 else None,
        sla_tracker=make_tracker() if idx >= 1 else None,
    )
    return Incident.restore(snapshot)
