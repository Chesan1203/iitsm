from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.domain.business_rules import BusinessRules
from app.domain.enums import Priority, SlaEventType, SlaStatus
from app.domain.models._validation import require_instance, require_naive_datetime
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.sla import SlaPolicy

if TYPE_CHECKING:
    from app.domain.models.incident import Incident


@dataclass(frozen=True)
class SlaCheckResult:
    status: SlaStatus
    new_events: list[SlaEventType]


def _clock(start: datetime, deadline: datetime, stopped_at: datetime | None, now: datetime):
    """(violated, in_warning_zone) for one SLA clock.

    The clock runs from `start` until `stopped_at` (or until `now` while it is still running).
    Violated means strictly after the deadline. The warning zone starts at 80 percent of the
    window and applies only while the clock is running and the deadline is not yet missed.
    """
    reference = stopped_at if stopped_at is not None else now
    violated = reference > deadline
    warn_at = start + (deadline - start) * BusinessRules.SLA_WARNING_FRACTION
    in_warning = stopped_at is None and not violated and reference >= warn_at
    return violated, in_warning


class SlaCalculator:
    def create_tracker(self, priority: Priority, policy: SlaPolicy, start: datetime) -> SlaTracker:
        """Both deadlines are counted from `start` (the incident's creation time)."""
        require_instance(priority, Priority, "priority")
        require_instance(policy, SlaPolicy, "policy")
        require_naive_datetime(start, "start")
        target = policy.target_for(priority)
        return SlaTracker(start + timedelta(minutes=target.response_minutes),
                          start + timedelta(minutes=target.resolution_minutes))

    def evaluate(self, incident: Incident, now: datetime) -> SlaCheckResult:
        """Pure: changes nothing. Returns the overall status and only the NEW events.

        - Response clock: creation -> acknowledgement. Resolution clock: creation -> RESOLVED
          (it runs again if the resolution is rejected, because resolved_at is cleared).
        - An event the tracker has already flagged is never returned again.
        - VIOLATED is sticky: it stays even if the incident is later resolved.
        - MET: both clocks stopped and no deadline was missed.
        - An incident without a tracker (not classified yet) has no SLA: ON_TRACK, no events.
        """
        require_naive_datetime(now, "now")
        tracker = incident.sla_tracker
        if tracker is None:
            return SlaCheckResult(SlaStatus.ON_TRACK, [])
        start = incident.created_at
        resp_violated, resp_warning = _clock(start, tracker.response_deadline,
                                             incident.acknowledged_at, now)
        res_violated, res_warning = _clock(start, tracker.resolution_deadline,
                                           incident.resolved_at, now)

        events: list[SlaEventType] = []
        if resp_violated and not tracker.response_violated:
            events.append(SlaEventType.RESPONSE_VIOLATED)
        elif resp_warning and not tracker.response_warned:
            events.append(SlaEventType.RESPONSE_WARNING)
        if res_violated and not tracker.resolution_violated:
            events.append(SlaEventType.RESOLUTION_VIOLATED)
        elif res_warning and not tracker.resolution_warned:
            events.append(SlaEventType.RESOLUTION_WARNING)

        if resp_violated or res_violated or tracker.response_violated or tracker.resolution_violated:
            status = SlaStatus.VIOLATED
        elif incident.acknowledged_at is not None and incident.resolved_at is not None:
            status = SlaStatus.MET
        elif resp_warning or res_warning:
            status = SlaStatus.WARNING
        else:
            status = SlaStatus.ON_TRACK
        return SlaCheckResult(status, events)
