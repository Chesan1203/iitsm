from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import Priority, SlaEventType, SlaStatus
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.sla import SlaPolicy

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_NOT_YET = "Implemented in task T6"


@dataclass(frozen=True)
class SlaCheckResult:
    status: SlaStatus
    new_events: list[SlaEventType]


class SlaCalculator:
    def create_tracker(self, priority: Priority, policy: SlaPolicy, start: datetime) -> SlaTracker:
        raise NotImplementedError(_NOT_YET)

    def evaluate(self, incident: Incident, now: datetime) -> SlaCheckResult:
        """Pure: changes nothing. Never repeats an event the tracker already flagged."""
        raise NotImplementedError(_NOT_YET)
