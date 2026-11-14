from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import IncidentStatus
from app.domain.models._validation import require_instance, require_text


@dataclass(frozen=True, kw_only=True)
class AuditRecord:
    id: int | None = None
    incident_id: int
    ticket_number: str
    timestamp: datetime
    actor_id: int
    actor_name: str
    action: str
    previous_status: IncidentStatus | None = None
    new_status: IncidentStatus | None = None
    description: str = ""

    def __post_init__(self):
        require_text(self.ticket_number, "ticket_number")
        require_instance(self.timestamp, datetime, "timestamp")
        require_text(self.actor_name, "actor_name")
        require_text(self.action, "action")
