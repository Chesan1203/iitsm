from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ChannelType, IncidentEventType
from app.domain.models._validation import require_instance, require_text


@dataclass(frozen=True, kw_only=True)
class Notification:
    id: int | None = None
    recipient_id: int
    incident_id: int
    event_type: IncidentEventType
    channel: ChannelType
    message: str
    created_at: datetime
    is_read: bool = False

    def __post_init__(self):
        require_instance(self.event_type, IncidentEventType, "event_type")
        require_instance(self.channel, ChannelType, "channel")
        require_text(self.message, "message")
        require_instance(self.created_at, datetime, "created_at")
