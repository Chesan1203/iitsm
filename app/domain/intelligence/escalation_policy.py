from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.domain.business_rules import BusinessRules as R
from app.domain.enums import AdminLevel, EscalationLevel, IncidentStatus, Priority

if TYPE_CHECKING:
    from app.domain.models.incident import Incident


@dataclass(frozen=True)
class EscalationDecision:
    new_level: EscalationLevel
    target_admin_level: AdminLevel
    reason: str


class EscalationPolicy:
    """Stateless. Applies only to a P1 incident still ASSIGNED after its response deadline.

    Once the deadline has passed the incident goes to TEAM_LEAD; every further 10 minutes it
    goes one level higher, up to IT_MANAGER. Returns a decision only when the target level is
    higher than the incident's current level, so it can be polled safely.
    """

    def evaluate(self, incident: Incident, now: datetime) -> EscalationDecision | None:
        tracker = incident.sla_tracker
        if (incident.priority is not Priority.P1 or incident.status is not IncidentStatus.ASSIGNED
                or tracker is None):
            return None
        overdue = now - tracker.response_deadline
        if overdue <= timedelta(0):
            return None
        periods = overdue // timedelta(minutes=R.ESCALATION_STEP_MINUTES)
        target = EscalationLevel(min(EscalationLevel.TEAM_LEAD.value + periods,
                                     EscalationLevel.IT_MANAGER.value))
        if target.value <= incident.escalation_level.value:
            return None
        minutes = int(overdue.total_seconds() // 60)
        late = f"{minutes} min after" if minutes >= 1 else "just past"
        return EscalationDecision(
            target, AdminLevel[target.name],
            f"P1 incident still unacknowledged {late} its response deadline; escalating to {target.name}")
