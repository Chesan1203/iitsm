from __future__ import annotations

import threading
from pathlib import Path

from app.domain.enums import ChannelType, IncidentEventType
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.domain.time_provider import TimeProvider
from app.services.channels.notification_channel import NotificationChannel


class SimulatedEmailChannel(NotificationChannel):
    """No email is sent. Each message is appended to a log file (default logs/emails.log) as a
    readable To / Subject / Body block, which is what a demo needs to show."""

    def __init__(self, log_path: str | Path, time_provider: TimeProvider):
        self._path = Path(log_path)
        self._time = time_provider
        self._lock = threading.Lock()        # the web server and the scheduler both write

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.EMAIL

    def send(self, recipient: User, incident: Incident, event_type: IncidentEventType,
             message: str) -> None:
        subject = f"[{incident.ticket_number}] {event_type.name.replace('_', ' ').title()}"
        block = (f"=== Simulated email ===\n"
                 f"Time:    {self._time.now():%Y-%m-%d %H:%M:%S}\n"
                 f"To:      {recipient.full_name} <{recipient.email}>\n"
                 f"Subject: {subject}\n\n"
                 f"{message}\n\n"
                 f"Incident: {incident.title}\n\n")
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as log:
                log.write(block)
