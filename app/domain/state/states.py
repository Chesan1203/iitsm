"""The State pattern: one class per IncidentStatus.

Each state overrides ONLY the actions that are legal there; everything else is inherited
from IncidentState and raises InvalidStateTransitionError. So NEW -> CLOSED is impossible
by construction, with no if/else chain anywhere.

Order of checks in every action (keeps error messages predictable):
  1. is the action legal in this state?   -> InvalidStateTransitionError
  2. is this actor allowed?               -> UnauthorizedOperationError
  3. is the data valid?                   -> InvalidInputError / workload errors
Then: change the incident, then announce the event.

States call the underscore helpers of Incident (_set, _add_note, _fire). Only code in
app/domain/state/ may do that: it is Python's version of 'package-private'.
"""
from __future__ import annotations

from datetime import datetime

from app.domain.enums import EscalationLevel, IncidentEventType, IncidentStatus, NoteType, Priority
from app.domain.exceptions import (
    InvalidInputError, InvalidStateTransitionError, TechnicianUnavailableError,
    WorkloadExceededError,
)
from app.domain.intelligence.escalation_policy import EscalationDecision
from app.domain.models._validation import require_instance, require_int_min, require_text
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.user import Technician
from app.domain.state import permissions as perm
from app.domain.state.incident_state import IncidentState
from app.domain.strategies.priority import PriorityResult

E = IncidentEventType


def _brief(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _check_can_take(technician, active_count) -> None:
    """Shared by assign_to and reassign."""
    require_instance(technician, Technician, "technician")
    require_int_min(active_count, 0, "active_count")
    if not technician.active or not technician.available:
        raise TechnicianUnavailableError(f"{technician.full_name} is not available for assignment")
    if active_count >= technician.max_workload:
        raise WorkloadExceededError(
            f"{technician.full_name} already has {active_count} active incidents "
            f"(maximum {technician.max_workload})")


def _submit_feedback(incident, actor, at, rating, comment) -> None:
    """Shared by VerifiedState and ClosedState."""
    if incident.feedback is not None:
        raise InvalidStateTransitionError("Feedback was already submitted for this incident")
    perm.require_reporter(incident, actor, "submit feedback")
    incident._set(feedback=Feedback(rating, comment, at))
    incident._fire(E.FEEDBACK_SUBMITTED, actor, incident.status, f"Feedback submitted: {rating}/5", at)


class OpenState(IncidentState):
    """Behaviour shared by every state except CLOSED."""

    # Investigation notes by the assigned technician are legal from ASSIGNED to RESOLVED.
    _technician_may_note = False

    def add_note(self, incident, actor, at, text, note_type) -> None:
        if note_type is NoteType.INVESTIGATION:
            if not self._technician_may_note:
                self._illegal("add_note")
            perm.require_assigned_technician(incident, actor, "add an investigation note")
        elif note_type is NoteType.INFO_RESPONSE:
            perm.require_reporter(incident, actor, "add information to the incident")
        else:
            raise InvalidInputError("Use request_info to ask the reporter a question", "note_type")
        note = InvestigationNote(author=actor, note_type=note_type, text=text, created_at=at)
        incident._add_note(note)
        incident._fire(E.NOTE_ADDED, actor, incident.status,
                       f"{note_type.name.title()} note added: {_brief(note.text)}", at)

    def escalate(self, incident, actor, at, decision) -> None:
        perm.require_admin_or_system(actor, "escalate an incident")
        require_instance(decision, EscalationDecision, "decision")
        require_instance(decision.new_level, EscalationLevel, "decision")
        if decision.new_level.value <= incident.escalation_level.value:
            raise InvalidInputError("Escalation must raise the escalation level", "decision")
        incident._set(escalation_level=decision.new_level)
        incident._fire(E.ESCALATED, actor, incident.status,
                       f"Escalated to {decision.new_level.name}: {decision.reason}", at)

    def change_priority(self, incident, actor, at, priority, reason, new_sla_tracker) -> None:
        if incident.priority is None:           # not classified yet: nothing to change
            self._illegal("change_priority")
        perm.require_admin_or_system(actor, "change an incident's priority")
        require_instance(priority, Priority, "priority")
        reason = require_text(reason, "reason")
        require_instance(new_sla_tracker, SlaTracker, "new_sla_tracker")
        if priority is incident.priority:
            raise InvalidInputError(f"Priority is already {priority.name}", "priority")
        old = incident.priority
        incident._set(priority=priority, sla_tracker=new_sla_tracker)
        incident._fire(E.PRIORITY_CHANGED, actor, incident.status,
                       f"Priority changed from {old.name} to {priority.name}: {reason}", at)

    def mark_possible_duplicate(self, incident, actor, at, other_ticket_number, score) -> None:
        perm.require_admin_or_system(actor, "flag a possible duplicate")
        other = require_text(other_ticket_number, "other_ticket_number")
        if other == incident.ticket_number:
            raise InvalidInputError("An incident cannot be a duplicate of itself", "other_ticket_number")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise InvalidInputError("Similarity score must be between 0 and 1", "score")
        incident._set(possible_duplicate_of=other)
        incident._fire(E.DUPLICATE_FLAGGED, actor, incident.status,
                       f"Possible duplicate of {other} (similarity {score:.2f})", at)

    def apply_sla_result(self, incident, at, result) -> None:
        raise NotImplementedError("Implemented in task T6")


class NewState(OpenState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.NEW

    def record_creation(self, incident, actor, at) -> None:
        perm.require_reporter_or_system(incident, actor, "record the creation of this incident")
        incident._fire(E.CREATED, actor, None,
                       f"Incident created by {actor.full_name} ({actor.username}): {_brief(incident.title)}", at)

    def classify(self, incident, actor, at, priority_result, sla_tracker) -> None:
        perm.require_system(actor, "classify an incident")
        require_instance(priority_result, PriorityResult, "priority_result")
        require_instance(sla_tracker, SlaTracker, "sla_tracker")
        previous = incident.status
        p = priority_result.priority
        incident._set(priority=p, priority_score=priority_result.score,
                      sla_tracker=sla_tracker, status=IncidentStatus.CLASSIFIED)
        incident._fire(E.CLASSIFIED, actor, previous,
                       f"Classified as {incident.category.name}; priority {p.name} ({p.label}): "
                       f"{priority_result.explanation}", at)


class ClassifiedState(OpenState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.CLASSIFIED

    def assign_to(self, incident, actor, at, technician, active_count) -> None:
        perm.require_admin_or_system(actor, "assign an incident")
        _check_can_take(technician, active_count)
        previous = incident.status
        incident._set(assigned_technician=technician, assigned_at=at, status=IncidentStatus.ASSIGNED)
        incident._fire(E.ASSIGNED, actor, previous,
                       f"Assigned to {technician.full_name} ({technician.username})", at)


class AssignedState(OpenState):
    _technician_may_note = True

    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.ASSIGNED

    def reassign(self, incident, actor, at, technician, active_count) -> None:
        perm.require_admin(actor, "reassign an incident")
        require_instance(technician, Technician, "technician")
        current = incident.assigned_technician
        if technician.id is not None and technician.id == current.id:
            raise InvalidInputError(f"Incident is already assigned to {current.full_name}", "technician")
        _check_can_take(technician, active_count)
        incident._set(assigned_technician=technician, assigned_at=at)
        incident._fire(E.REASSIGNED, actor, incident.status,
                       f"Reassigned from {current.full_name} to {technician.full_name} "
                       f"({technician.username})", at)

    def acknowledge(self, incident, actor, at) -> None:
        perm.require_assigned_technician(incident, actor, "acknowledge this incident")
        previous = incident.status
        incident._set(acknowledged_at=at, status=IncidentStatus.ACKNOWLEDGED)
        incident._fire(E.ACKNOWLEDGED, actor, previous, f"Acknowledged by {actor.full_name}", at)


class AcknowledgedState(OpenState):
    _technician_may_note = True

    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.ACKNOWLEDGED

    def start_investigation(self, incident, actor, at) -> None:
        perm.require_assigned_technician(incident, actor, "start the investigation")
        previous = incident.status
        incident._set(status=IncidentStatus.IN_PROGRESS)
        incident._fire(E.INVESTIGATION_STARTED, actor, previous, "Investigation started", at)


class InProgressState(OpenState):
    _technician_may_note = True

    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.IN_PROGRESS

    def request_info(self, incident, actor, at, question) -> None:
        perm.require_assigned_technician(incident, actor, "request information from the reporter")
        note = InvestigationNote(author=actor, note_type=NoteType.INFO_REQUEST, text=question, created_at=at)
        incident._add_note(note)
        incident._fire(E.INFO_REQUESTED, actor, incident.status,
                       f"Information requested: {_brief(note.text)}", at)

    def respond_to_info(self, incident, actor, at, answer) -> None:
        if not incident.has_pending_info_request:
            raise InvalidStateTransitionError("There is no pending information request on this incident")
        perm.require_reporter(incident, actor, "respond to an information request")
        note = InvestigationNote(author=actor, note_type=NoteType.INFO_RESPONSE, text=answer, created_at=at)
        incident._add_note(note)
        incident._fire(E.INFO_RESPONDED, actor, incident.status,
                       f"Information provided: {_brief(note.text)}", at)

    def resolve(self, incident, actor, at, summary, details) -> None:
        perm.require_assigned_technician(incident, actor, "resolve this incident")
        resolution = Resolution(summary, details, actor, at)
        previous = incident.status
        incident._set(resolution=resolution, resolved_at=at, status=IncidentStatus.RESOLVED)
        incident._fire(E.RESOLVED, actor, previous, f"Resolved: {_brief(resolution.summary)}", at)


class ResolvedState(OpenState):
    _technician_may_note = True

    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.RESOLVED

    def verify(self, incident, actor, at) -> None:
        perm.require_reporter_or_admin(incident, actor, "verify the resolution")
        previous = incident.status
        incident._set(verified_at=at, status=IncidentStatus.VERIFIED)
        incident._fire(E.VERIFIED, actor, previous, f"Resolution verified by {actor.full_name}", at)

    def reject_resolution(self, incident, actor, at, reason) -> None:
        perm.require_reporter(incident, actor, "reject the resolution")
        reason = require_text(reason, "reason")
        rejected = incident.resolution
        previous = incident.status
        # The rejected resolution is not kept on the incident (it would be stale);
        # its summary is preserved in the audit description instead.
        incident._set(resolution=None, resolved_at=None, status=IncidentStatus.IN_PROGRESS)
        detail = f" (rejected resolution: {_brief(rejected.summary)})" if rejected else ""
        incident._fire(E.RESOLUTION_REJECTED, actor, previous,
                       f"Resolution rejected: {_brief(reason)}{detail}", at)


class VerifiedState(OpenState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.VERIFIED

    def close(self, incident, actor, at) -> None:
        perm.require_reporter_or_admin(incident, actor, "close the incident")
        previous = incident.status
        incident._set(closed_at=at, status=IncidentStatus.CLOSED)
        incident._fire(E.CLOSED, actor, previous, f"Incident closed by {actor.full_name}", at)

    def submit_feedback(self, incident, actor, at, rating, comment) -> None:
        _submit_feedback(incident, actor, at, rating, comment)


class ClosedState(IncidentState):
    """Terminal state. The only thing still allowed is the reporter's one-time feedback."""

    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.CLOSED

    def submit_feedback(self, incident, actor, at, rating, comment) -> None:
        _submit_feedback(incident, actor, at, rating, comment)
