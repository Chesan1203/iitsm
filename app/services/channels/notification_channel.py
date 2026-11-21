from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.enums import ChannelType, IncidentEventType
from app.domain.models.incident import Incident
from app.domain.models.user import User


class NotificationChannel(ABC):
    """One way of delivering a notification (Strategy pattern, with Adapter flavour: a real
    email or SMS gateway would be wrapped in a class like this one). Adding a mechanism means
    adding one class and listing it in services/wiring.py."""

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    def send(self, recipient: User, incident: Incident, event_type: IncidentEventType,
             message: str) -> None: ...
