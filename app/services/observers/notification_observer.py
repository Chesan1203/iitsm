from __future__ import annotations

import logging
from collections.abc import Sequence

from app.domain.enums import AdminLevel, IncidentEventType as E, Role
from app.domain.events import IncidentEvent
from app.domain.models.user import User
from app.domain.observer import IncidentObserver
from app.ports.repositories import UserRepository
from app.services.channels.notification_channel import NotificationChannel

logger = logging.getLogger(__name__)

# Who hears about each event. Events that are not listed (CLASSIFIED, INVESTIGATION_STARTED,
# NOTE_ADDED, FEEDBACK_SUBMITTED) are audit-only: nobody is notified.
REPORTER, TECHNICIAN, ADMINS, LEVEL_ADMINS = "reporter", "technician", "admins", "level_admins"
RECIPIENTS: dict[E, tuple[str, ...]] = {
    E.CREATED: (REPORTER, ADMINS),
    E.ASSIGNED: (TECHNICIAN, REPORTER),
    E.REASSIGNED: (TECHNICIAN, REPORTER),
    E.ACKNOWLEDGED: (REPORTER,),
    E.INFO_REQUESTED: (REPORTER,),
    E.INFO_RESPONDED: (TECHNICIAN,),
    E.RESOLVED: (REPORTER,),
    E.RESOLUTION_REJECTED: (TECHNICIAN,),
    E.VERIFIED: (TECHNICIAN,),
    E.CLOSED: (REPORTER, TECHNICIAN),
    E.PRIORITY_CHANGED: (TECHNICIAN, REPORTER),
    E.SLA_WARNING: (TECHNICIAN, ADMINS),
    E.SLA_VIOLATED: (TECHNICIAN, ADMINS),
    E.ESCALATED: (LEVEL_ADMINS, TECHNICIAN),
    E.DUPLICATE_FLAGGED: (ADMINS,),
}

TEMPLATES: dict[E, str] = {
    E.CREATED: "Incident {ticket} was created: {title}",
    E.ASSIGNED: "{ticket} \"{title}\" was assigned to {technician}",
    E.REASSIGNED: "{ticket} \"{title}\" was reassigned to {technician}",
    E.ACKNOWLEDGED: "{technician} acknowledged {ticket} and will start working on it",
    E.INFO_REQUESTED: "More information is needed on {ticket}. {detail}",
    E.INFO_RESPONDED: "The reporter answered your question on {ticket}. {detail}",
    E.RESOLVED: "{ticket} \"{title}\" has been resolved. Please verify the fix.",
    E.RESOLUTION_REJECTED: "The resolution of {ticket} was rejected and it is back in progress. {detail}",
    E.VERIFIED: "The reporter verified the resolution of {ticket}",
    E.CLOSED: "{ticket} \"{title}\" is now closed",
    E.PRIORITY_CHANGED: "The priority of {ticket} is now {priority}. {detail}",
    E.SLA_WARNING: "SLA warning: {ticket} is close to a deadline. {detail}",
    E.SLA_VIOLATED: "SLA violated: {ticket} missed a deadline. {detail}",
    E.ESCALATED: "{ticket} has been escalated to {escalation}. {detail}",
    E.DUPLICATE_FLAGGED: "{ticket} may be a duplicate. {detail}",
}


class _Fields(dict):
    def __missing__(self, key):
        return ""


class NotificationObserver(IncidentObserver):
    """Observer pattern: decides who to tell about each event, writes a friendly message and
    sends it through EVERY channel. A failure in one channel or for one recipient is logged and
    never stops the others (and never undoes the incident change)."""

    def __init__(self, users: UserRepository, channels: Sequence[NotificationChannel]):
        self._users, self._channels = users, list(channels)

    def on_event(self, event: IncidentEvent) -> None:
        template = TEMPLATES.get(event.event_type)
        if template is None:
            return
        message = " ".join(template.format_map(self._fields(event)).split())
        for recipient in self._recipients(event):
            for channel in self._channels:
                try:
                    channel.send(recipient, event.incident, event.event_type, message)
                except Exception:
                    logger.exception("%s failed to notify %s about %s on %s",
                                     type(channel).__name__, recipient.username,
                                     event.event_type.name, event.incident.ticket_number)

    # ---- helpers ------------------------------------------------------------------------
    @staticmethod
    def _fields(event: IncidentEvent) -> _Fields:
        incident = event.incident
        tech = incident.assigned_technician
        priority = incident.priority
        return _Fields(
            ticket=incident.ticket_number, title=incident.title, detail=event.description,
            technician=tech.full_name if tech else "a technician",
            priority=f"{priority.name} ({priority.label})" if priority else "not set",
            escalation=incident.escalation_level.name.replace("_", " ").title())

    def _recipients(self, event: IncidentEvent) -> list[User]:
        """The people named in the table, without duplicates and without deactivated accounts."""
        incident = event.incident
        chosen: list[User] = []
        for who in RECIPIENTS.get(event.event_type, ()):
            if who == REPORTER:
                chosen.append(incident.reporter)
            elif who == TECHNICIAN and incident.assigned_technician is not None:
                chosen.append(incident.assigned_technician)
            elif who == ADMINS:
                chosen.extend(self._users.find_by_role(Role.ADMINISTRATOR))
            elif who == LEVEL_ADMINS:
                level = AdminLevel.__members__.get(incident.escalation_level.name)
                if level is not None:                 # EscalationLevel.TECHNICIAN has no admin level
                    chosen.extend(self._users.find_admins_by_level(level))
        unique: dict[int, User] = {}
        for user in chosen:
            if user.active and user.id not in unique:
                unique[user.id] = user
        return list(unique.values())
