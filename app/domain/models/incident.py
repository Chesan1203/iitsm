from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import (
    EscalationLevel, IncidentEventType, IncidentStatus, Level, NoteType, Priority,
)
from app.domain.events import IncidentEvent
from app.domain.exceptions import InvalidInputError
from app.domain.models._entity import Entity
from app.domain.models._validation import (
    require_instance, require_int_min, require_naive_datetime, require_text,
)
from app.domain.models.category import Category
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Technician, User
from app.domain.observer import IncidentObserver
from app.domain.state.state_factory import IncidentStateFactory

if TYPE_CHECKING:
    from app.domain.intelligence.escalation_policy import EscalationDecision
    from app.domain.sla.sla_calculator import SlaCheckResult
    from app.domain.state.incident_state import IncidentState
    from app.domain.strategies.priority import PriorityResult

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({IncidentStatus.ASSIGNED, IncidentStatus.ACKNOWLEDGED,
                              IncidentStatus.IN_PROGRESS})



class Incident(Entity):
    def __init__(self, title: str, description: str, reporter: User, category: Category,
                 affected_service: ITService, impact: Level, urgency: Level,
                 affected_users: int, created_at: datetime):
        super().__init__(None)
        self._ticket_number: str | None = None
        self._title = require_text(title, "title")
        self._description = require_text(description, "description")
        self._reporter = require_instance(reporter, User, "reporter")
        self._category = require_instance(category, Category, "category")
        self._affected_service = require_instance(affected_service, ITService, "affected_service")
        self._impact = require_instance(impact, Level, "impact")
        self._urgency = require_instance(urgency, Level, "urgency")
        self._affected_users = require_int_min(affected_users, 1, "affected_users")
        self._created_at = require_naive_datetime(created_at, "created_at")
        self._priority: Priority | None = None
        self._priority_score: int | None = None
        self._status = IncidentStatus.NEW
        self._assigned_technician: Technician | None = None
        self._assigned_at: datetime | None = None
        self._acknowledged_at: datetime | None = None
        self._resolved_at: datetime | None = None
        self._verified_at: datetime | None = None
        self._closed_at: datetime | None = None
        self._escalation_level = EscalationLevel.TECHNICIAN
        self._possible_duplicate_of: str | None = None
        self._notes: list[InvestigationNote] = []
        self._resolution: Resolution | None = None
        self._feedback: Feedback | None = None
        self._sla_tracker: SlaTracker | None = None
        self._observers: list[IncidentObserver] = []

    # ---- identity ---------------------------------------------------------
    def assign_identity(self, id: int, ticket_number: str) -> None:
        """Called by the repository on first save. Write-once."""
        self.assign_id(id)
        self._ticket_number = require_text(ticket_number, "ticket_number")

    # ---- read-only properties --------------------------------------------
    @property
    def ticket_number(self) -> str | None: return self._ticket_number
    @property
    def title(self) -> str: return self._title
    @property
    def description(self) -> str: return self._description
    @property
    def reporter(self) -> User: return self._reporter
    @property
    def category(self) -> Category: return self._category
    @property
    def affected_service(self) -> ITService: return self._affected_service
    @property
    def impact(self) -> Level: return self._impact
    @property
    def urgency(self) -> Level: return self._urgency
    @property
    def affected_users(self) -> int: return self._affected_users
    @property
    def priority(self) -> Priority | None: return self._priority
    @property
    def priority_score(self) -> int | None: return self._priority_score
    @property
    def status(self) -> IncidentStatus: return self._status
    @property
    def created_at(self) -> datetime: return self._created_at
    @property
    def assigned_technician(self) -> Technician | None: return self._assigned_technician
    @property
    def assigned_at(self) -> datetime | None: return self._assigned_at
    @property
    def acknowledged_at(self) -> datetime | None: return self._acknowledged_at
    @property
    def resolved_at(self) -> datetime | None: return self._resolved_at
    @property
    def verified_at(self) -> datetime | None: return self._verified_at
    @property
    def closed_at(self) -> datetime | None: return self._closed_at
    @property
    def escalation_level(self) -> EscalationLevel: return self._escalation_level
    @property
    def possible_duplicate_of(self) -> str | None: return self._possible_duplicate_of
    @property
    def resolution(self) -> Resolution | None: return self._resolution
    @property
    def feedback(self) -> Feedback | None: return self._feedback
    @property
    def sla_tracker(self) -> SlaTracker | None: return self._sla_tracker

    @property
    def notes(self) -> list[InvestigationNote]:
        return list(self._notes)

    @property
    def is_open(self) -> bool:
        return self._status is not IncidentStatus.CLOSED

    @property
    def is_active(self) -> bool:
        return self._status in _ACTIVE_STATUSES

    # ---- plumbing ---------------------------------------------------------
    def add_observer(self, observer: IncidentObserver) -> None:
        require_instance(observer, IncidentObserver, "observer")
        if not any(o is observer for o in self._observers):
            self._observers.append(observer)

    def snapshot(self) -> IncidentSnapshot:
        return IncidentSnapshot(
            id=self._id, ticket_number=self._ticket_number, title=self._title,
            description=self._description, reporter=self._reporter, category=self._category,
            affected_service=self._affected_service, impact=self._impact, urgency=self._urgency,
            affected_users=self._affected_users, priority=self._priority,
            priority_score=self._priority_score, status=self._status, created_at=self._created_at,
            assigned_technician=self._assigned_technician, assigned_at=self._assigned_at,
            acknowledged_at=self._acknowledged_at, resolved_at=self._resolved_at,
            verified_at=self._verified_at, closed_at=self._closed_at,
            escalation_level=self._escalation_level,
            possible_duplicate_of=self._possible_duplicate_of, notes=tuple(self._notes),
            resolution=self._resolution, feedback=self._feedback,
            sla_tracker=None if self._sla_tracker is None else self._sla_tracker.copy(),
        )

    @classmethod
    def restore(cls, snapshot: IncidentSnapshot) -> "Incident":
        """Rebuild an incident in any state. Observers are NOT restored; re-attach them."""
        require_instance(snapshot, IncidentSnapshot, "snapshot")
        require_instance(snapshot.status, IncidentStatus, "status")
        inc = cls.__new__(cls)
        inc._id = snapshot.id
        inc._ticket_number = snapshot.ticket_number
        inc._title = snapshot.title
        inc._description = snapshot.description
        inc._reporter = snapshot.reporter
        inc._category = snapshot.category
        inc._affected_service = snapshot.affected_service
        inc._impact = snapshot.impact
        inc._urgency = snapshot.urgency
        inc._affected_users = snapshot.affected_users
        inc._created_at = snapshot.created_at
        inc._priority = snapshot.priority
        inc._priority_score = snapshot.priority_score
        inc._status = snapshot.status
        inc._assigned_technician = snapshot.assigned_technician
        inc._assigned_at = snapshot.assigned_at
        inc._acknowledged_at = snapshot.acknowledged_at
        inc._resolved_at = snapshot.resolved_at
        inc._verified_at = snapshot.verified_at
        inc._closed_at = snapshot.closed_at
        inc._escalation_level = snapshot.escalation_level
        inc._possible_duplicate_of = snapshot.possible_duplicate_of
        inc._notes = list(snapshot.notes)
        inc._resolution = snapshot.resolution
        inc._feedback = snapshot.feedback
        inc._sla_tracker = None if snapshot.sla_tracker is None else snapshot.sla_tracker.copy()
        inc._observers = []
        return inc

    def __repr__(self) -> str:
        return f"Incident({self._ticket_number or 'unsaved'}, {self._status.name}, {self._title!r})"

    @property
    def has_pending_info_request(self) -> bool:
        """True when the latest information note is a question the reporter has not answered."""
        for note in reversed(self._notes):
            if note.note_type in (NoteType.INFO_REQUEST, NoteType.INFO_RESPONSE):
                return note.note_type is NoteType.INFO_REQUEST
        return False

    # ---- internals used only by the state classes (app/domain/state/) ---------
    # Python has no 'package-private', so this is a convention: nothing outside
    # app/domain/state/ may call the underscore-prefixed methods below.
    _MUTABLE_FIELDS = frozenset({
        "status", "priority", "priority_score", "assigned_technician", "assigned_at",
        "acknowledged_at", "resolved_at", "verified_at", "closed_at", "escalation_level",
        "possible_duplicate_of", "resolution", "feedback", "sla_tracker",
    })

    @property
    def _state(self) -> "IncidentState":
        """The state object for the current status (derived, never stored)."""
        return IncidentStateFactory.for_status(self._status)

    def _set(self, **changes) -> None:
        """Change whitelisted fields, all or nothing."""
        unknown = set(changes) - self._MUTABLE_FIELDS
        if unknown:
            raise InvalidInputError(f"Cannot change incident field(s): {sorted(unknown)}")
        for name, value in changes.items():
            setattr(self, f"_{name}", value)

    def _add_note(self, note: InvestigationNote) -> None:
        self._notes.append(note)

    def _fire(self, event_type: IncidentEventType, actor: User,
              previous_status: IncidentStatus | None, description: str, at: datetime) -> None:
        """Announce what just happened to every observer, in registration order.

        Called by a state AFTER the change is complete, so observers see the new state.
        An observer that fails is logged and skipped: the incident change stands and the
        remaining observers still run.
        """
        event = IncidentEvent(incident=self, event_type=event_type, actor=actor,
                              previous_status=previous_status, new_status=self._status,
                              description=description, timestamp=at)
        for observer in list(self._observers):      # a copy: observers may attach others
            try:
                observer.on_event(event)
            except Exception:
                logger.exception("Observer %s failed on %s for incident %s",
                                 type(observer).__name__, event_type.name,
                                 self._ticket_number or "(unsaved)")

    # ---- behaviour: every action is delegated to the current state -------
    def record_creation(self, actor: User, at: datetime) -> None:
        self._state.record_creation(self, actor, at)

    def classify(self, actor: User, at: datetime, priority_result: PriorityResult,
                 sla_tracker: SlaTracker) -> None:
        self._state.classify(self, actor, at, priority_result, sla_tracker)

    def assign_to(self, actor: User, at: datetime, technician: Technician, active_count: int) -> None:
        self._state.assign_to(self, actor, at, technician, active_count)

    def reassign(self, actor: User, at: datetime, technician: Technician, active_count: int) -> None:
        self._state.reassign(self, actor, at, technician, active_count)

    def acknowledge(self, actor: User, at: datetime) -> None:
        self._state.acknowledge(self, actor, at)

    def start_investigation(self, actor: User, at: datetime) -> None:
        self._state.start_investigation(self, actor, at)

    def add_note(self, actor: User, at: datetime, text: str, note_type: NoteType) -> None:
        self._state.add_note(self, actor, at, text, note_type)

    def request_info(self, actor: User, at: datetime, question: str) -> None:
        self._state.request_info(self, actor, at, question)

    def respond_to_info(self, actor: User, at: datetime, answer: str) -> None:
        self._state.respond_to_info(self, actor, at, answer)

    def resolve(self, actor: User, at: datetime, summary: str, details: str) -> None:
        self._state.resolve(self, actor, at, summary, details)

    def verify(self, actor: User, at: datetime) -> None:
        self._state.verify(self, actor, at)

    def reject_resolution(self, actor: User, at: datetime, reason: str) -> None:
        self._state.reject_resolution(self, actor, at, reason)

    def close(self, actor: User, at: datetime) -> None:
        self._state.close(self, actor, at)

    def submit_feedback(self, actor: User, at: datetime, rating: int, comment: str) -> None:
        self._state.submit_feedback(self, actor, at, rating, comment)

    def escalate(self, actor: User, at: datetime, decision: EscalationDecision) -> None:
        self._state.escalate(self, actor, at, decision)

    def change_priority(self, actor: User, at: datetime, priority: Priority, reason: str,
                        new_sla_tracker: SlaTracker) -> None:
        self._state.change_priority(self, actor, at, priority, reason, new_sla_tracker)

    def mark_possible_duplicate(self, actor: User, at: datetime, other_ticket_number: str,
                                score: float) -> None:
        self._state.mark_possible_duplicate(self, actor, at, other_ticket_number, score)

    def apply_sla_result(self, at: datetime, result: SlaCheckResult) -> None:
        self._state.apply_sla_result(self, at, result)
