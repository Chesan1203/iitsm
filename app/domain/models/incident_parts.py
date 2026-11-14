from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import NoteType, SlaStatus
from app.domain.models._validation import (
    optional_text, require_instance, require_int_between, require_text,
)
from app.domain.models.user import User


class SlaTracker:
    """Owned by an Incident. Only the Incident may change it (via _apply)."""

    def __init__(self, response_deadline: datetime, resolution_deadline: datetime,
                 response_warned: bool = False, resolution_warned: bool = False,
                 response_violated: bool = False, resolution_violated: bool = False,
                 status: SlaStatus = SlaStatus.ON_TRACK):
        self._response_deadline = require_instance(response_deadline, datetime, "response_deadline")
        self._resolution_deadline = require_instance(resolution_deadline, datetime, "resolution_deadline")
        self._response_warned = bool(response_warned)
        self._resolution_warned = bool(resolution_warned)
        self._response_violated = bool(response_violated)
        self._resolution_violated = bool(resolution_violated)
        self._status = require_instance(status, SlaStatus, "status")

    @property
    def response_deadline(self) -> datetime: return self._response_deadline
    @property
    def resolution_deadline(self) -> datetime: return self._resolution_deadline
    @property
    def response_warned(self) -> bool: return self._response_warned
    @property
    def resolution_warned(self) -> bool: return self._resolution_warned
    @property
    def response_violated(self) -> bool: return self._response_violated
    @property
    def resolution_violated(self) -> bool: return self._resolution_violated
    @property
    def status(self) -> SlaStatus: return self._status

    def _apply(self, status: SlaStatus, response_warned: bool, resolution_warned: bool,
               response_violated: bool, resolution_violated: bool) -> None:
        """Only Incident.apply_sla_result may call this."""
        self._status = require_instance(status, SlaStatus, "status")
        self._response_warned = bool(response_warned)
        self._resolution_warned = bool(resolution_warned)
        self._response_violated = bool(response_violated)
        self._resolution_violated = bool(resolution_violated)

    def copy(self) -> "SlaTracker":
        return SlaTracker(self._response_deadline, self._resolution_deadline,
                          self._response_warned, self._resolution_warned,
                          self._response_violated, self._resolution_violated, self._status)

    def _key(self) -> tuple:
        return (self._response_deadline, self._resolution_deadline, self._response_warned,
                self._resolution_warned, self._response_violated, self._resolution_violated,
                self._status)

    def __eq__(self, other) -> bool:
        return isinstance(other, SlaTracker) and self._key() == other._key()

    __hash__ = None

    def __repr__(self) -> str:
        return f"SlaTracker(status={self._status.name}, respond_by={self._response_deadline}, resolve_by={self._resolution_deadline})"


@dataclass(frozen=True, kw_only=True)
class InvestigationNote:
    id: int | None = None
    author: User
    note_type: NoteType
    text: str
    created_at: datetime

    def __post_init__(self):
        require_instance(self.author, User, "author")
        require_instance(self.note_type, NoteType, "note_type")
        require_text(self.text, "text")
        require_instance(self.created_at, datetime, "created_at")


@dataclass(frozen=True)
class Resolution:
    summary: str
    details: str
    resolved_by: User
    resolved_at: datetime

    def __post_init__(self):
        require_text(self.summary, "summary")
        optional_text(self.details, "details")
        require_instance(self.resolved_by, User, "resolved_by")
        require_instance(self.resolved_at, datetime, "resolved_at")


@dataclass(frozen=True)
class Feedback:
    rating: int
    comment: str
    submitted_at: datetime

    def __post_init__(self):
        require_int_between(self.rating, 1, 5, "rating")
        optional_text(self.comment, "comment")
        require_instance(self.submitted_at, datetime, "submitted_at")
