"""P3 T6: the SLA monitor job, the escalation job and the scheduler."""
import threading
import time
from types import SimpleNamespace

import pytest

from app.domain.business_rules import BusinessRules
from app.domain.enums import (
    EscalationLevel, IncidentEventType as E, IncidentStatus as S, Level, SlaEventType, SlaStatus,
)
from app.domain.exceptions import PersistenceError
from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.models.sla import SlaEvent
from app.domain.sla.sla_calculator import SlaCalculator
from app.services.jobs.escalation_job import EscalationJob
from app.services.jobs.scheduler import JobScheduler
from app.services.jobs.sla_monitor_job import SlaMonitorJob

from .helpers import actions, at, create, finish, new_incident

ADMINS = {"admin1", "admin2", "admin3"}


@pytest.fixture
def jobs(stack):
    repos = stack.repos
    return SimpleNamespace(
        sla=SlaMonitorJob(repos.incidents, repos.sla_events, SlaCalculator(), stack.clock, stack.registrar),
        escalation=EscalationJob(repos.incidents, EscalationPolicy(), stack.clock, stack.registrar))


def go_to(stack, minutes):
    stack.clock.current = at(minutes)


def stored(stack, incident):
    return stack.repos.incidents.find_by_id(incident.id)


def sla_rows(stack, incident):
    return [e.event_type for e in stack.repos.sla_events.find_by_incident(incident.id)]


# ====================================================================================================
# SLA monitor
# ====================================================================================================

def test_nothing_happens_early_in_the_window(stack, jobs):
    incident = create(stack)                                                     # P1: respond in 5, resolve in 30
    go_to(stack, 2)                                                              # 40 percent
    assert jobs.sla.run_once() == 0
    assert sla_rows(stack, incident) == [] and stored(stack, incident).sla_tracker.status is SlaStatus.ON_TRACK


def test_a_warning_is_recorded_once_at_80_percent_and_not_again(stack, jobs):
    incident = create(stack)
    go_to(stack, 4)                                                              # 80 percent of the 5-minute response window
    assert jobs.sla.run_once() == 1
    assert jobs.sla.run_once() == 0 and jobs.sla.run_once() == 0                 # nothing repeated
    assert sla_rows(stack, incident) == [SlaEventType.RESPONSE_WARNING]
    assert actions(stack, incident).count("SLA_WARNING") == 1
    assert stack.rec.recipients_of(E.SLA_WARNING) == {"tech1"} | ADMINS
    tracker = stored(stack, incident).sla_tracker
    assert tracker.status is SlaStatus.WARNING and tracker.response_warned


def test_a_violation_is_recorded_once_after_the_deadline(stack, jobs):
    incident = create(stack)
    go_to(stack, 4)
    jobs.sla.run_once()                                                          # the warning
    go_to(stack, 5.5)
    assert jobs.sla.run_once() == 1                                              # the violation
    assert jobs.sla.run_once() == 0
    assert sla_rows(stack, incident) == [SlaEventType.RESPONSE_WARNING, SlaEventType.RESPONSE_VIOLATED]
    assert actions(stack, incident).count("SLA_VIOLATED") == 1
    assert stored(stack, incident).sla_tracker.status is SlaStatus.VIOLATED
    assert stack.rec.recipients_of(E.SLA_VIOLATED) == {"tech1"} | ADMINS


def test_jumping_straight_past_the_deadline_records_only_the_violation(stack, jobs):
    incident = create(stack)
    go_to(stack, 6)
    assert jobs.sla.run_once() == 1
    assert sla_rows(stack, incident) == [SlaEventType.RESPONSE_VIOLATED]


def test_acknowledging_stops_the_response_clock_and_the_resolution_clock_runs_on(stack, jobs):
    incident = create(stack)
    go_to(stack, 1)
    stack.svc.acknowledge(stack.w.tech, incident.id)
    stack.svc.start_investigation(stack.w.tech, incident.id)
    go_to(stack, 4.5)
    assert jobs.sla.run_once() == 0                                              # no response events: it was acknowledged
    go_to(stack, 24)                                                             # 80 percent of the 30-minute resolution window
    assert jobs.sla.run_once() == 1
    go_to(stack, 31)
    assert jobs.sla.run_once() == 1
    assert sla_rows(stack, incident) == [SlaEventType.RESOLUTION_WARNING, SlaEventType.RESOLUTION_VIOLATED]


def test_an_incident_resolved_in_time_ends_as_met_without_any_event(stack, jobs):
    incident = create(stack)
    go_to(stack, 1)
    stack.svc.acknowledge(stack.w.tech, incident.id)
    stack.svc.start_investigation(stack.w.tech, incident.id)
    go_to(stack, 10)
    stack.svc.resolve(stack.w.tech, incident.id, "Fixed", "Details")
    before = len(actions(stack, incident))
    assert jobs.sla.run_once() == 0
    assert stored(stack, incident).sla_tracker.status is SlaStatus.MET           # the status is saved...
    assert len(actions(stack, incident)) == before and sla_rows(stack, incident) == []   # ...with no audit noise
    go_to(stack, 100)
    assert jobs.sla.run_once() == 0 and stored(stack, incident).sla_tracker.status is SlaStatus.MET


def test_closed_and_unclassified_incidents_are_left_alone(stack, jobs):
    finished = create(stack)
    finish(stack, finished)
    unclassified = new_incident(stack.w, "Not classified yet")                   # NEW, no tracker
    go_to(stack, 500)
    assert jobs.sla.run_once() == 0                                              # closed: not examined; NEW: no SLA yet
    assert sla_rows(stack, finished) == [] and sla_rows(stack, unclassified) == []
    assert stored(stack, unclassified).status is S.NEW and stored(stack, unclassified).sla_tracker is None


def test_it_counts_every_event_across_incidents(stack, jobs):
    for n in range(3):
        create(stack, f"Issue number {n}", description=f"Distinct description {n} xyz{n}")
    go_to(stack, 6)
    assert jobs.sla.run_once() == 3 and jobs.sla.run_once() == 0


def test_an_event_row_without_tracker_flags_is_not_duplicated_and_the_tracker_is_repaired(stack, jobs):
    """Crash recovery: the event row was written but the incident was never saved."""
    incident = create(stack)
    stack.repos.sla_events.save(SlaEvent(incident_id=incident.id, event_type=SlaEventType.RESPONSE_WARNING,
                                         recorded_at=at(4)))
    go_to(stack, 4)
    assert jobs.sla.run_once() == 0                                              # not recorded a second time
    assert sla_rows(stack, incident) == [SlaEventType.RESPONSE_WARNING]
    assert stored(stack, incident).sla_tracker.response_warned is True           # flags brought back in line
    assert jobs.sla.run_once() == 0


def test_one_failing_incident_does_not_stop_the_others_and_is_repaired_next_run(stack, jobs):
    first = create(stack, "First issue", description="First description aaa")
    second = create(stack, "Second issue", description="Second description bbb")
    go_to(stack, 6)
    real_save, failing = stack.repos.incidents.save, {"on": True}

    def flaky_save(incident):
        if failing["on"] and incident.id == first.id:
            raise PersistenceError("disk full")
        return real_save(incident)
    stack.repos.incidents.save = flaky_save
    assert jobs.sla.run_once() == 1                                              # the second incident was handled
    assert stored(stack, second).sla_tracker.status is SlaStatus.VIOLATED
    assert stored(stack, first).sla_tracker.status is SlaStatus.ON_TRACK         # its save failed
    failing["on"] = False
    assert jobs.sla.run_once() == 0                                              # event row already exists: no duplicate...
    assert stored(stack, first).sla_tracker.status is SlaStatus.VIOLATED         # ...but the incident is brought up to date
    assert sla_rows(stack, first) == [SlaEventType.RESPONSE_VIOLATED]


# ====================================================================================================
# Escalation
# ====================================================================================================

def _escalations(stack):
    return [(kind, name) for kind, name, _ in stack.rec.sent if kind is E.ESCALATED]


def test_an_unacknowledged_p1_escalates_through_the_chain_in_order(stack, jobs):
    incident = create(stack)                                                     # P1, assigned, response deadline at minute 5
    go_to(stack, 5)
    assert jobs.escalation.run_once() == 0                                       # exactly on the deadline is not late yet
    expected = [(5.5, EscalationLevel.TEAM_LEAD, {"admin1", "tech1"}),
                (15.5, EscalationLevel.SYSTEM_ADMIN, {"admin2", "tech1"}),
                (25.5, EscalationLevel.IT_MANAGER, {"admin3", "tech1"})]
    for minute, level, who in expected:
        go_to(stack, minute)
        before = len(_escalations(stack))
        assert jobs.escalation.run_once() == 1
        assert stored(stack, incident).escalation_level is level
        assert {name for _, name in _escalations(stack)[before:]} == who
        assert jobs.escalation.run_once() == 0                                   # polling again changes nothing
    go_to(stack, 120)
    assert jobs.escalation.run_once() == 0                                       # IT_MANAGER is the top
    assert actions(stack, incident).count("ESCALATED") == 3


def test_only_unacknowledged_p1_incidents_are_escalated(stack, jobs):
    p2 = create(stack, "A lesser issue", urgency=Level.LOW, affected_users=10, description="Distinct lesser text")
    acknowledged = create(stack, "Acknowledged in time", description="Another distinct text qrs")
    go_to(stack, 1)
    stack.svc.acknowledge(stack.w.tech, acknowledged.id)
    go_to(stack, 200)
    assert jobs.escalation.run_once() == 0
    assert stored(stack, p2).escalation_level is EscalationLevel.TECHNICIAN
    assert stored(stack, acknowledged).escalation_level is EscalationLevel.TECHNICIAN


def test_acknowledging_after_an_escalation_stops_further_escalation(stack, jobs):
    incident = create(stack)
    go_to(stack, 5.5)
    jobs.escalation.run_once()
    go_to(stack, 6)
    stack.svc.acknowledge(stack.w.tech, incident.id)
    go_to(stack, 60)
    assert jobs.escalation.run_once() == 0
    assert stored(stack, incident).escalation_level is EscalationLevel.TEAM_LEAD


def test_a_failing_escalation_does_not_stop_the_other_incidents(stack, jobs):
    first = create(stack, "First urgent", description="First urgent description aaa")
    second = create(stack, "Second urgent", description="Second urgent description bbb")
    go_to(stack, 6)
    real_save = stack.repos.incidents.save

    def flaky_save(incident):
        if incident.id == first.id:
            raise PersistenceError("disk full")
        return real_save(incident)
    stack.repos.incidents.save = flaky_save
    assert jobs.escalation.run_once() == 1
    assert stored(stack, second).escalation_level is EscalationLevel.TEAM_LEAD
    assert stored(stack, first).escalation_level is EscalationLevel.TECHNICIAN


# ====================================================================================================
# Scheduler
# ====================================================================================================

def _wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_scheduler_runs_both_jobs_repeatedly_and_stops_cleanly():
    calls, lock = {"sla": 0, "esc": 0}, threading.Lock()

    def count(key):
        def run():
            with lock:
                calls[key] += 1
            return 0
        return run
    scheduler = JobScheduler(count("sla"), count("esc"), interval_seconds=0.05)
    assert scheduler.running is False
    scheduler.start()
    scheduler.start()                                                            # starting twice is harmless
    try:
        assert scheduler.running
        assert _wait_for(lambda: calls["sla"] >= 3 and calls["esc"] >= 3)
    finally:
        scheduler.stop()
    assert scheduler.running is False
    scheduler.stop()                                                             # stopping twice is harmless
    frozen = dict(calls)
    time.sleep(0.3)
    assert calls == frozen                                                       # nothing runs after stop


def test_a_job_that_keeps_failing_does_not_stop_the_scheduler_or_the_other_job():
    calls, lock = {"bad": 0, "good": 0}, threading.Lock()

    def bad():
        with lock:
            calls["bad"] += 1
        raise RuntimeError("boom")

    def good():
        with lock:
            calls["good"] += 1
        return 0
    scheduler = JobScheduler(bad, good, interval_seconds=0.05)
    scheduler.start()
    try:
        assert _wait_for(lambda: calls["bad"] >= 3 and calls["good"] >= 3)      # the failing job is retried, too
    finally:
        scheduler.stop()


def test_scheduler_defaults_to_the_business_rule_interval():
    scheduler = JobScheduler(lambda: 0, lambda: 0)
    for job_id in ("sla_check", "escalation_check"):
        job = scheduler._scheduler.get_job(job_id)
        assert job.trigger.interval.total_seconds() == BusinessRules.SCHEDULER_INTERVAL_SECONDS == 30
        assert job.max_instances == 1 and job.coalesce is True
