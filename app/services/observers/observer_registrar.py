from __future__ import annotations

from collections.abc import Sequence

from app.domain.models.incident import Incident
from app.domain.observer import IncidentObserver


class ObserverRegistrar:
    """Observers are never stored in the database, so every incident that is created or loaded
    must be given them again before anything is done to it. Forgetting this means no audit
    records and no notifications, so services always go through attach()."""

    def __init__(self, observers: Sequence[IncidentObserver]):
        self._observers = list(observers)

    def attach(self, incident: Incident) -> Incident:
        for observer in self._observers:
            incident.add_observer(observer)
        return incident
