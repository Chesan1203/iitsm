from __future__ import annotations

from app.domain.events import IncidentEvent
from app.domain.models.audit import AuditRecord
from app.domain.observer import IncidentObserver
from app.ports.repositories import AuditRepository


class AuditObserver(IncidentObserver):
    """Observer pattern: turns every incident event into one audit record. The incident must
    already be saved (the record needs its id and ticket number)."""

    def __init__(self, audits: AuditRepository):
        self._audits = audits

    def on_event(self, event: IncidentEvent) -> None:
        incident = event.incident
        self._audits.save(AuditRecord(
            incident_id=incident.id, ticket_number=incident.ticket_number,
            timestamp=event.timestamp, actor_id=event.actor.id, actor_name=event.actor.full_name,
            action=event.event_type.name, previous_status=event.previous_status,
            new_status=event.new_status, description=event.description))
