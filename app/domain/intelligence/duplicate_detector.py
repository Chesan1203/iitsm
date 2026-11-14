from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_NOT_YET = "Implemented in task T8"


@dataclass(frozen=True)
class DuplicateMatch:
    other_ticket_number: str
    score: float


class DuplicateDetector:
    def find_similar(self, incident: Incident, recent_incidents: list[Incident]) -> list[DuplicateMatch]:
        raise NotImplementedError(_NOT_YET)
