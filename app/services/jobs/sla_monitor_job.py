from __future__ import annotations

import logging

from app.domain.models.incident import Incident
from app.domain.models.sla import SlaEvent
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.time_provider import TimeProvider
from app.ports.repositories import IncidentRepository, SlaEventRepository
from app.services.observers.observer_registrar import ObserverRegistrar

logger = logging.getLogger(__name__)


class SlaMonitorJob:
    """Checks every open incident against its SLA deadlines.

    Warnings and violations are recorded ONCE only, by two independent guards: the tracker's
    flags (the calculator never reports an event the tracker already flagged) and the
    sla_events table (an `exists` check, backed by a unique rule in the database).
    """

    def __init__(self, incidents: IncidentRepository, sla_events: SlaEventRepository,
                 calculator: SlaCalculator, time_provider: TimeProvider,
                 registrar: ObserverRegistrar):
        self._incidents, self._events, self._calculator = incidents, sla_events, calculator
        self._time, self._registrar = time_provider, registrar

    def run_once(self) -> int:
        """Run one check. Returns how many SLA events were recorded. A problem with one
        incident is logged and does not stop the others."""
        now = self._time.now()
        recorded = 0
        for incident in self._incidents.find_open():
            try:
                recorded += self._check(incident, now)
            except Exception:
                logger.exception("SLA check failed for %s", incident.ticket_number)
        return recorded

    def _check(self, incident: Incident, now) -> int:
        tracker = incident.sla_tracker
        if tracker is None:                                    # not classified yet: no SLA
            return 0
        result = self._calculator.evaluate(incident, now)
        status_changed = result.status is not tracker.status    # for example MET after a timely resolution
        if not result.new_events and not status_changed:
            return 0
        recorded = 0
        for event_type in dict.fromkeys(result.new_events):
            if not self._events.exists(incident.id, event_type):
                self._events.save(SlaEvent(incident_id=incident.id, event_type=event_type,
                                           recorded_at=now))
                recorded += 1
        # Applying the whole result also repairs a tracker whose flags were lost after the
        # event row was written (a crash between the two steps).
        self._registrar.attach(incident).apply_sla_result(now, result)
        self._incidents.save(incident)
        return recorded
