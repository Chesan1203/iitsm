from __future__ import annotations

from app.domain.enums import ChannelType, IncidentEventType
from app.domain.models.incident import Incident
from app.domain.models.notification import Notification
from app.domain.models.user import User
from app.domain.time_provider import TimeProvider
from app.ports.repositories import NotificationRepository
from app.services.channels.notification_channel import NotificationChannel


class InAppChannel(NotificationChannel):
    """Stores the notification so it shows up in the user's bell and notifications page."""

    def __init__(self, notifications: NotificationRepository, time_provider: TimeProvider):
        self._notifications, self._time = notifications, time_provider

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.IN_APP

    def send(self, recipient: User, incident: Incident, event_type: IncidentEventType,
             message: str) -> None:
        self._notifications.save(Notification(
            recipient_id=recipient.id, incident_id=incident.id, event_type=event_type,
            channel=ChannelType.IN_APP, message=message, created_at=self._time.now()))
