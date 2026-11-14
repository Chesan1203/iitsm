from abc import ABC, abstractmethod

from app.domain.events import IncidentEvent


class IncidentObserver(ABC):
    @abstractmethod
    def on_event(self, event: IncidentEvent) -> None:
        """React to something that happened to an incident."""
