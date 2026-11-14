from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import IncidentEventType, IncidentStatus

if TYPE_CHECKING:
    from app.domain.models.incident import Incident
    from app.domain.models.user import User


@dataclass(frozen=True)
class IncidentEvent:
    incident: Incident
    event_type: IncidentEventType
    actor: User
    previous_status: IncidentStatus | None
    new_status: IncidentStatus | None
    description: str
    timestamp: datetime
