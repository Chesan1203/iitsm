from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from app.domain.business_rules import BusinessRules

logger = logging.getLogger(__name__)


class JobScheduler:
    """Runs the SLA and escalation checks in a background thread, every 30 seconds by default
    (BusinessRules.SCHEDULER_INTERVAL_SECONDS). The same jobs can also be run on demand
    through the admin service, which is how the demo fast-forwards."""

    def __init__(self, sla_check: Callable[[], int], escalation_check: Callable[[], int],
                 interval_seconds: float = BusinessRules.SCHEDULER_INTERVAL_SECONDS):
        self._scheduler = BackgroundScheduler()
        for job_id, function in (("sla_check", sla_check), ("escalation_check", escalation_check)):
            self._scheduler.add_job(
                self._guarded(job_id, function), "interval", seconds=interval_seconds,
                id=job_id, max_instances=1, coalesce=True)    # never overlap, never pile up

    @staticmethod
    def _guarded(job_id: str, function: Callable[[], int]) -> Callable[[], None]:
        def run() -> None:
            try:
                function()
            except Exception:                                 # one bad run must not stop future runs
                logger.exception("Scheduled job %s failed", job_id)
        return run

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
