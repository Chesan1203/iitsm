import pytest

from app.domain.enums import (
    IncidentEventType as E, IncidentStatus as S, Priority, SlaEventType as SE, SlaStatus,
)
from app.domain.exceptions import (
    InvalidInputError, InvalidStateTransitionError, MissingSlaConfigurationError,
)
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.observer import IncidentObserver
from app.domain.sla.sla_calculator import SlaCalculator, SlaCheckResult
from app.domain.models.user import User
from tests.domain.helpers import (
    T0, at, make_admin, make_default_policy, make_incident, make_incident_in, make_priority_result,
    make_tracker,
)
from datetime import timedelta

CALC = SlaCalculator()
SYSTEM = User.system()
SEC = timedelta(seconds=1)


def when(minutes: float):
    return T0 + timedelta(minutes=minutes)


def check(incident, minutes):
    return CALC.evaluate(incident, when(minutes))


def check_and_apply(incident, minutes):
    result = check(incident, minutes)
    incident.apply_sla_result(when(minutes), result)
    return result


class Recorder(IncidentObserver):
    def __init__(self):
        self.events = []

    def on_event(self, event):
        self.events.append(event)


# ---- trackers ------------------------------------------------------------------

def test_create_tracker_counts_both_deadlines_from_the_start_time():
    policy = make_default_policy()
    expected = {Priority.P1: (5, 30), Priority.P2: (15, 120), Priority.P3: (60, 480),
                Priority.P4: (240, 1440)}
    for priority, (response, resolution) in expected.items():
        tracker = CALC.create_tracker(priority, policy, T0)
        assert tracker.response_deadline == T0 + timedelta(minutes=response)
        assert tracker.resolution_deadline == T0 + timedelta(minutes=resolution)
        assert tracker.status is SlaStatus.ON_TRACK
        assert not (tracker.response_warned or tracker.resolution_warned
                    or tracker.response_violated or tracker.resolution_violated)


def test_create_tracker_needs_a_target_and_valid_arguments():
    partial = SlaPolicy("Partial", False, {Priority.P1: SlaTarget(5, 30)})
    with pytest.raises(MissingSlaConfigurationError):
        CALC.create_tracker(Priority.P4, partial, T0)
    with pytest.raises(InvalidInputError):
        CALC.create_tracker("P1", partial, T0)
    with pytest.raises(InvalidInputError):
        CALC.create_tracker(Priority.P1, partial, "now")


# ---- evaluating the response clock (P1: 5 minutes, warning at 4:00) ----------------

def test_nothing_happens_at_fifty_percent():
    inc = make_incident_in(S.ASSIGNED)
    result = check(inc, 2.5)
    assert result == SlaCheckResult(SlaStatus.ON_TRACK, [])


def test_unclassified_incident_has_no_sla():
    assert check(make_incident(), 100) == SlaCheckResult(SlaStatus.ON_TRACK, [])


def test_warning_starts_at_exactly_eighty_percent():
    inc = make_incident_in(S.ASSIGNED)
    assert check(inc, 4).new_events == [SE.RESPONSE_WARNING]
    assert check(inc, 4).status is SlaStatus.WARNING
    assert check(inc, 4 - 1 / 60).new_events == []                 # one second earlier


def test_violation_only_strictly_after_the_deadline():
    inc = make_incident_in(S.ASSIGNED)
    at_deadline = check(inc, 5)
    assert at_deadline.status is SlaStatus.WARNING and SE.RESPONSE_VIOLATED not in at_deadline.new_events
    after = CALC.evaluate(inc, when(5) + SEC)
    assert after.status is SlaStatus.VIOLATED
    assert SE.RESPONSE_VIOLATED in after.new_events


def test_events_are_never_repeated_and_evaluate_is_pure():
    inc = make_incident_in(S.ASSIGNED)
    before = inc.snapshot()
    first = check(inc, 4)
    assert inc.snapshot() == before                                # evaluate changed nothing
    inc.apply_sla_result(when(4), first)
    again = check(inc, 4.5)
    assert again == SlaCheckResult(SlaStatus.WARNING, [])
    inc.apply_sla_result(when(4.5), again)
    violated = check(inc, 6)
    assert violated.new_events == [SE.RESPONSE_VIOLATED]           # the warning is not repeated
    inc.apply_sla_result(when(6), violated)
    assert check(inc, 7) == SlaCheckResult(SlaStatus.VIOLATED, [])


def test_acknowledgement_stops_the_response_clock():
    inc = make_incident_in(S.ASSIGNED)
    inc.acknowledge(inc.assigned_technician, when(3))
    assert check(inc, 4.5).new_events == []                        # no response warning any more
    assert check(inc, 10) == SlaCheckResult(SlaStatus.ON_TRACK, [])


def test_late_acknowledgement_is_still_a_response_violation():
    inc = make_incident_in(S.ASSIGNED)
    inc.acknowledge(inc.assigned_technician, when(6))
    result = check(inc, 7)                                         # the job runs after the fact
    assert result.new_events == [SE.RESPONSE_VIOLATED] and result.status is SlaStatus.VIOLATED


# ---- the resolution clock (30 minutes, warning at 24:00) -----------------------------

def test_resolution_warning_and_violation_are_independent_of_the_response_clock():
    inc = make_incident_in(S.ASSIGNED)
    inc.acknowledge(inc.assigned_technician, when(1))
    assert check(inc, 23.9).new_events == []
    warning = check_and_apply(inc, 24)
    assert warning.new_events == [SE.RESOLUTION_WARNING] and warning.status is SlaStatus.WARNING
    assert check(inc, 30).new_events == []
    violated = check_and_apply(inc, 30.5)
    assert violated.new_events == [SE.RESOLUTION_VIOLATED] and violated.status is SlaStatus.VIOLATED


def test_response_and_resolution_warnings_are_separate_events():
    """Regression for the single-WARNING design: both warnings must be recordable."""
    inc = make_incident_in(S.ASSIGNED)
    assert check_and_apply(inc, 4).new_events == [SE.RESPONSE_WARNING]
    assert inc.sla_tracker.response_warned and not inc.sla_tracker.resolution_warned
    inc.acknowledge(inc.assigned_technician, when(4.5))
    result = check_and_apply(inc, 24)
    assert result.new_events == [SE.RESOLUTION_WARNING]
    assert inc.sla_tracker.resolution_warned


def test_resolved_in_time_ends_as_met():
    inc = make_incident_in(S.IN_PROGRESS)
    inc.resolve(inc.assigned_technician, when(20), "Fixed", "Details")
    result = check_and_apply(inc, 60)
    assert result == SlaCheckResult(SlaStatus.MET, [])
    assert inc.sla_tracker.status is SlaStatus.MET


def test_resolved_late_is_a_violation_even_if_the_job_runs_afterwards():
    inc = make_incident_in(S.IN_PROGRESS)
    inc.resolve(inc.assigned_technician, when(31), "Fixed", "Details")
    result = check(inc, 60)
    assert result.new_events == [SE.RESOLUTION_VIOLATED] and result.status is SlaStatus.VIOLATED


def test_violated_is_sticky_through_verification_and_closure():
    inc = make_incident_in(S.ASSIGNED)
    check_and_apply(inc, 6)                                        # response violated
    inc.acknowledge(inc.assigned_technician, when(7))
    inc.start_investigation(inc.assigned_technician, when(8))
    inc.resolve(inc.assigned_technician, when(20), "Fixed", "Details")
    inc.verify(inc.reporter, when(21))
    assert check(inc, 22).status is SlaStatus.VIOLATED
    inc.close(inc.reporter, when(23))
    assert check(inc, 24).status is SlaStatus.VIOLATED


def test_rejecting_a_resolution_restarts_the_resolution_clock():
    inc = make_incident_in(S.IN_PROGRESS)
    inc.resolve(inc.assigned_technician, when(20), "Fixed", "Details")
    assert check_and_apply(inc, 21).status is SlaStatus.MET
    inc.reject_resolution(inc.reporter, when(22), "Still failing")
    result = check_and_apply(inc, 25)
    assert result.new_events == [SE.RESOLUTION_WARNING] and result.status is SlaStatus.WARNING


# ---- a whole timeline, polled like the scheduler does ---------------------------------

def test_polling_every_minute_records_each_event_exactly_once():
    inc = make_incident_in(S.ASSIGNED)                              # never acknowledged
    recorder = Recorder()
    inc.add_observer(recorder)
    recorded = []
    for minute in range(0, 41):
        for event_type in check_and_apply(inc, minute).new_events:
            recorded.append((minute, event_type))
    assert recorded == [(4, SE.RESPONSE_WARNING), (6, SE.RESPONSE_VIOLATED),
                        (24, SE.RESOLUTION_WARNING), (31, SE.RESOLUTION_VIOLATED)]
    assert [e.event_type for e in recorder.events] == [
        E.SLA_WARNING, E.SLA_VIOLATED, E.SLA_WARNING, E.SLA_VIOLATED]
    assert inc.sla_tracker.status is SlaStatus.VIOLATED


# ---- apply_sla_result ------------------------------------------------------------------

def test_apply_sla_result_updates_flags_status_and_announces_events():
    inc = make_incident_in(S.ASSIGNED)
    recorder = Recorder()
    inc.add_observer(recorder)
    inc.apply_sla_result(when(6), SlaCheckResult(
        SlaStatus.VIOLATED, [SE.RESPONSE_WARNING, SE.RESPONSE_VIOLATED]))
    tracker = inc.sla_tracker
    assert tracker.response_warned and tracker.response_violated
    assert not tracker.resolution_warned and not tracker.resolution_violated
    assert tracker.status is SlaStatus.VIOLATED
    assert [e.event_type for e in recorder.events] == [E.SLA_WARNING, E.SLA_VIOLATED]
    assert all(e.actor is SYSTEM and e.timestamp == when(6) for e in recorder.events)
    assert "response deadline" in recorder.events[0].description
    assert "missed" in recorder.events[1].description
    assert inc.status is S.ASSIGNED


def test_status_only_change_updates_the_tracker_without_an_event():
    inc = make_incident_in(S.ASSIGNED)
    recorder = Recorder()
    inc.add_observer(recorder)
    inc.apply_sla_result(when(1), SlaCheckResult(SlaStatus.WARNING, []))
    assert inc.sla_tracker.status is SlaStatus.WARNING and recorder.events == []


def test_apply_sla_result_rules():
    with pytest.raises(InvalidStateTransitionError):
        make_incident().apply_sla_result(when(1), SlaCheckResult(SlaStatus.ON_TRACK, []))   # no tracker
    with pytest.raises(InvalidStateTransitionError):
        make_incident_in(S.CLOSED).apply_sla_result(when(1), SlaCheckResult(SlaStatus.MET, []))
    inc = make_incident_in(S.ASSIGNED)
    with pytest.raises(InvalidInputError):
        inc.apply_sla_result(when(1), "violated")
    with pytest.raises(InvalidInputError):
        inc.apply_sla_result(when(1), SlaCheckResult(SlaStatus.WARNING, ["WARNING"]))


def test_trackers_are_private_copies():
    tracker = make_tracker()
    inc = make_incident()
    inc.classify(SYSTEM, at(1), make_priority_result(), tracker)
    inc.apply_sla_result(when(6), SlaCheckResult(SlaStatus.VIOLATED, [SE.RESPONSE_VIOLATED]))
    assert not tracker.response_violated and inc.sla_tracker.response_violated


# ---- a changed priority keeps history ---------------------------------------------------

def test_change_priority_keeps_violations_and_restarts_warnings():
    inc = make_incident_in(S.ASSIGNED)
    check_and_apply(inc, 6)                                         # response violated at 6 min
    new_tracker = CALC.create_tracker(Priority.P3, make_default_policy(), T0)   # +60 / +480
    inc.change_priority(make_admin(), when(7), Priority.P3, "Lower impact", new_tracker)
    tracker = inc.sla_tracker
    assert tracker.response_deadline == T0 + timedelta(minutes=60)
    assert tracker.response_violated and tracker.status is SlaStatus.VIOLATED
    assert not tracker.response_warned
    assert check(inc, 8) == SlaCheckResult(SlaStatus.VIOLATED, [])  # nothing repeated
