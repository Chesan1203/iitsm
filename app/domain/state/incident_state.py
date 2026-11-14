from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import IncidentStatus, NoteType, Priority
from app.domain.exceptions import InvalidStateTransitionError

if TYPE_CHECKING:
    from app.domain.intelligence.escalation_policy import EscalationDecision
    from app.domain.models.incident import Incident
    from app.domain.models.incident_parts import SlaTracker
    from app.domain.models.user import Technician, User
    from app.domain.sla.sla_calculator import SlaCheckResult
    from app.domain.strategies.priority import PriorityResult


class IncidentState(ABC):
    """State pattern base. Every action is illegal unless a concrete state overrides it."""

    @property
    @abstractmethod
    def status(self) -> IncidentStatus: ...

    _PHRASES = {
        "record_creation": "record the creation of",
        "assign_to": "assign",
        "start_investigation": "start investigating",
        "add_note": "add a note to",
        "request_info": "request information on",
        "respond_to_info": "respond to an information request on",
        "reject_resolution": "reject the resolution of",
        "submit_feedback": "submit feedback on",
        "change_priority": "change the priority of",
        "mark_possible_duplicate": "flag a possible duplicate on",
        "apply_sla_result": "apply an SLA result to",
    }

    def _illegal(self, action: str):
        phrase = self._PHRASES.get(action, action.replace("_", " "))
        raise InvalidStateTransitionError(
            f"Cannot {phrase} an incident that is {self.status.name}")

    def record_creation(self, incident: Incident, actor: User, at: datetime) -> None:
        self._illegal("record_creation")

    def classify(self, incident: Incident, actor: User, at: datetime,
                 priority_result: PriorityResult, sla_tracker: SlaTracker) -> None:
        self._illegal("classify")

    def assign_to(self, incident: Incident, actor: User, at: datetime,
                  technician: Technician, active_count: int) -> None:
        self._illegal("assign_to")

    def reassign(self, incident: Incident, actor: User, at: datetime,
                 technician: Technician, active_count: int) -> None:
        self._illegal("reassign")

    def acknowledge(self, incident: Incident, actor: User, at: datetime) -> None:
        self._illegal("acknowledge")

    def start_investigation(self, incident: Incident, actor: User, at: datetime) -> None:
        self._illegal("start_investigation")

    def add_note(self, incident: Incident, actor: User, at: datetime, text: str,
                 note_type: NoteType) -> None:
        self._illegal("add_note")

    def request_info(self, incident: Incident, actor: User, at: datetime, question: str) -> None:
        self._illegal("request_info")

    def respond_to_info(self, incident: Incident, actor: User, at: datetime, answer: str) -> None:
        self._illegal("respond_to_info")

    def resolve(self, incident: Incident, actor: User, at: datetime, summary: str,
                details: str) -> None:
        self._illegal("resolve")

    def verify(self, incident: Incident, actor: User, at: datetime) -> None:
        self._illegal("verify")

    def reject_resolution(self, incident: Incident, actor: User, at: datetime, reason: str) -> None:
        self._illegal("reject_resolution")

    def close(self, incident: Incident, actor: User, at: datetime) -> None:
        self._illegal("close")

    def submit_feedback(self, incident: Incident, actor: User, at: datetime, rating: int,
                        comment: str) -> None:
        self._illegal("submit_feedback")

    def escalate(self, incident: Incident, actor: User, at: datetime,
                 decision: EscalationDecision) -> None:
        self._illegal("escalate")

    def change_priority(self, incident: Incident, actor: User, at: datetime, priority: Priority,
                        reason: str, new_sla_tracker: SlaTracker) -> None:
        self._illegal("change_priority")

    def mark_possible_duplicate(self, incident: Incident, actor: User, at: datetime,
                                other_ticket_number: str, score: float) -> None:
        self._illegal("mark_possible_duplicate")

    def apply_sla_result(self, incident: Incident, at: datetime, result: SlaCheckResult) -> None:
        self._illegal("apply_sla_result")
