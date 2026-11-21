"""Which buttons and forms an incident page shows to a given person.

This is a DISPLAY HINT only: it keeps the page free of buttons that would just fail. It is not
security. Every action still goes through a service that checks the actor, and through the
incident's state objects that decide whether the action is legal in the current status.
"""
from __future__ import annotations

from app.domain.enums import IncidentStatus as S, Role
from app.domain.models.incident import Incident
from app.domain.models.user import User

# Action names used by the templates.
ACKNOWLEDGE, START, NOTE, REQUEST_INFO, RESOLVE = "acknowledge", "start", "note", "request_info", "resolve"
RESPOND, ADD_INFO, VERIFY, REJECT, CLOSE, FEEDBACK = "respond", "add_info", "verify", "reject", "close", "feedback"
ASSIGN, AUTO_ASSIGN, RECOMMEND, OVERRIDE_PRIORITY = "assign", "auto_assign", "recommend", "override_priority"

_NOTE_STATUSES = {S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.RESOLVED}


def allowed_actions(user: User, incident: Incident) -> set[str]:
    status = incident.status
    actions: set[str] = set()
    is_reporter = incident.reporter.id == user.id
    technician = incident.assigned_technician
    is_assigned_tech = technician is not None and technician.id == user.id
    is_admin = user.role is Role.ADMINISTRATOR and not user.is_system

    if is_assigned_tech:
        if status is S.ASSIGNED:
            actions.add(ACKNOWLEDGE)
        if status is S.ACKNOWLEDGED:
            actions.add(START)
        if status in _NOTE_STATUSES:
            actions.add(NOTE)
        if status is S.IN_PROGRESS:
            actions |= {REQUEST_INFO, RESOLVE}

    if is_reporter:
        if status is not S.CLOSED:
            actions.add(ADD_INFO)
        if status is S.IN_PROGRESS and incident.has_pending_info_request:
            actions.add(RESPOND)
        if status is S.RESOLVED:
            actions |= {VERIFY, REJECT}
        if status is S.VERIFIED:
            actions.add(CLOSE)
        if status in (S.VERIFIED, S.CLOSED) and incident.feedback is None:
            actions.add(FEEDBACK)

    if is_admin:
        if status is S.RESOLVED:
            actions.add(VERIFY)
        if status is S.VERIFIED:
            actions.add(CLOSE)
        if status is S.CLASSIFIED:
            actions |= {ASSIGN, AUTO_ASSIGN, RECOMMEND}
        if status is S.ASSIGNED:
            actions |= {ASSIGN, RECOMMEND}                       # assigning again is a reassignment
        if status is not S.CLOSED and incident.priority is not None:
            actions.add(OVERRIDE_PRIORITY)
    return actions


STEPS = [S.NEW, S.CLASSIFIED, S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.RESOLVED, S.VERIFIED, S.CLOSED]


def progress_steps(incident: Incident) -> list[dict]:
    """The eight lifecycle steps, each marked done, current or upcoming (for the progress bar)."""
    position = STEPS.index(incident.status)
    return [{"status": step, "state": "done" if i < position else "current" if i == position else "todo"}
            for i, step in enumerate(STEPS)]
