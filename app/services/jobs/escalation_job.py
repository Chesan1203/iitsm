from __future__ import annotations

import logging

from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.models.user import User
from app.domain.time_provider import TimeProvider
from app.ports.repositories import IncidentRepository
from app.services.observers.observer_registrar import ObserverRegistrar

logger = logging.getLogger(__name__)


class EscalationJob:
    """Escalates P1 incidents that nobody has acknowledged in time. The policy (P1 only,
    TEAM_LEAD after the response deadline, one level higher every 10 minutes, capped at
    IT_MANAGER) lives in the domain; this class only applies its decisions."""

    def __init__(self, incidents: IncidentRepository, policy: EscalationPolicy,
                 time_provider: TimeProvider, registrar: ObserverRegistrar):
        self._incidents, self._policy = incidents, policy
        self._time, self._registrar = time_provider, registrar

    def run_once(self) -> int:
        """Returns how many incidents were escalated. A problem with one incident is logged
        and does not stop the others."""
        now = self._time.now()
        escalated = 0
        for incident in self._incidents.find_unacknowledged():
            try:
                decision = self._policy.evaluate(incident, now)
                if decision is None:
                    continue
                self._registrar.attach(incident).escalate(User.system(), now, decision)
                self._incidents.save(incident)
                escalated += 1
            except Exception:
                logger.exception("Escalation failed for %s", incident.ticket_number)
        return escalated
