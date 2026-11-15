from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.domain.business_rules import BusinessRules as R
from app.domain.enums import IncidentStatus
from app.domain.models._validation import require_naive_datetime
from app.domain.models.it_service import ITService

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_FINISHED = frozenset({IncidentStatus.RESOLVED, IncidentStatus.VERIFIED, IncidentStatus.CLOSED})


@dataclass(frozen=True)
class CorrelationGroup:
    service: ITService
    incidents: list[Incident]
    is_probable_service_problem: bool


class CorrelationDetector:
    """Groups the incidents that are still unresolved, created in the last 60 minutes, by
    affected service. A service with 2 incidents gets a group; with 3 or more it is flagged as
    a probable service-level problem. Resolved, verified and closed incidents are ignored
    (their problem is fixed)."""

    def find_groups(self, open_incidents: list[Incident], now: datetime) -> list[CorrelationGroup]:
        require_naive_datetime(now, "now")
        window_start = now - timedelta(minutes=R.CORRELATION_WINDOW_MINUTES)
        by_service: dict[tuple, list[Incident]] = defaultdict(list)
        for incident in open_incidents:
            if incident.status in _FINISHED or not window_start <= incident.created_at <= now:
                continue
            service = incident.affected_service
            by_service[(service.id, service.name)].append(incident)
        groups = []
        for incidents in by_service.values():
            if len(incidents) < 2:
                continue
            incidents.sort(key=lambda i: i.created_at)
            groups.append(CorrelationGroup(
                incidents[0].affected_service, incidents,
                len(incidents) >= R.CORRELATION_MIN_INCIDENTS))
        groups.sort(key=lambda g: (not g.is_probable_service_problem, -len(g.incidents), g.service.name))
        return groups
