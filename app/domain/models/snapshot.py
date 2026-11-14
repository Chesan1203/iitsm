from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import EscalationLevel, IncidentStatus, Level, Priority
from app.domain.models.category import Category
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.user import Technician, User


@dataclass(frozen=True, kw_only=True)
class IncidentSnapshot:
    """Plain copy of every Incident field. Always construct with keyword arguments."""
    id: int | None = None
    ticket_number: str | None = None
    title: str
    description: str
    reporter: User
    category: Category
    affected_service: ITService
    impact: Level
    urgency: Level
    affected_users: int
    priority: Priority | None = None
    priority_score: int | None = None
    status: IncidentStatus = IncidentStatus.NEW
    created_at: datetime
    assigned_technician: Technician | None = None
    assigned_at: datetime | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    verified_at: datetime | None = None
    closed_at: datetime | None = None
    escalation_level: EscalationLevel = EscalationLevel.TECHNICIAN
    possible_duplicate_of: str | None = None
    notes: tuple[InvestigationNote, ...] = ()
    resolution: Resolution | None = None
    feedback: Feedback | None = None
    sla_tracker: SlaTracker | None = None

    def __post_init__(self):
        # Accept any iterable of notes, but always store a tuple so equality is stable.
        object.__setattr__(self, "notes", tuple(self.notes))
