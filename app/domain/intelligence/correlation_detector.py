from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.models.it_service import ITService

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_NOT_YET = "Implemented in task T8 (stretch)"


@dataclass(frozen=True)
class CorrelationGroup:
    service: ITService
    incidents: list[Incident]
    is_probable_service_problem: bool


class CorrelationDetector:
    def find_groups(self, open_incidents: list[Incident], now: datetime) -> list[CorrelationGroup]:
        raise NotImplementedError(_NOT_YET)
