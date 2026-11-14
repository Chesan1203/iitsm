import dataclasses
import logging

import pytest

from app.domain.enums import (
    EscalationLevel, IncidentEventType as E, IncidentStatus as S, NoteType, Priority,
)
from app.domain.events import IncidentEvent
from app.domain.exceptions import (
    InvalidInputError, InvalidStateTransitionError, PersistenceError, UnauthorizedOperationError,
    WorkloadExceededError,
)
from app.domain.intelligence.escalation_policy import EscalationDecision
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.domain.observer import IncidentObserver
from tests.domain.helpers import (
    at, make_admin, make_employee, make_incident, make_incident_in, make_priority_result,
    make_technician, make_tracker,
)

SYSTEM = User.system()


class Recorder(IncidentObserver):
    def __init__(self):
        self.events: list[IncidentEvent] = []
        self.status_when_called: list[S] = []

    def on_event(self, event):
        self.events.append(event)
        self.status_when_called.append(event.incident.status)   # what the observer can see

    @property
    def types(self):
        return [e.event_type for e in self.events]


class Exploding(IncidentObserver):
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def on_event(self, event):
        self.calls += 1
        raise self.error


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def watched(incident):
    recorder = Recorder()
    incident.add_observer(recorder)
    return recorder


# ---- one event per action, in order -------------------------------------------

def test_happy_path_emits_exactly_one_event_per_action_in_order():
    inc = make_incident()
    rec = watched(inc)
    emp, tech = inc.reporter, make_technician()
    inc.record_creation(emp, at(0))
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    inc.assign_to(SYSTEM, at(2), tech, 0)
    inc.acknowledge(tech, at(3))
    inc.start_investigation(tech, at(4))
    inc.resolve(tech, at(5), "Restarted DB pool", "Pool was exhausted")
    inc.verify(emp, at(6))
    inc.close(emp, at(7))
    inc.submit_feedback(emp, at(8), 5, "Fast fix")

    assert rec.types == [E.CREATED, E.CLASSIFIED, E.ASSIGNED, E.ACKNOWLEDGED,
                         E.INVESTIGATION_STARTED, E.RESOLVED, E.VERIFIED, E.CLOSED,
                         E.FEEDBACK_SUBMITTED]
    transitions = [(e.previous_status, e.new_status) for e in rec.events]
    assert transitions == [
        (None, S.NEW), (S.NEW, S.CLASSIFIED), (S.CLASSIFIED, S.ASSIGNED),
        (S.ASSIGNED, S.ACKNOWLEDGED), (S.ACKNOWLEDGED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.RESOLVED), (S.RESOLVED, S.VERIFIED), (S.VERIFIED, S.CLOSED),
        (S.CLOSED, S.CLOSED)]
    assert [e.timestamp for e in rec.events] == [at(i) for i in range(9)]
    assert [e.actor for e in rec.events] == [emp, SYSTEM, SYSTEM, tech, tech, tech, emp, emp, emp]
    assert all(e.incident is inc and e.description for e in rec.events)


def test_events_that_do_not_change_status_report_the_same_status_twice():
    inc = make_incident_in(S.IN_PROGRESS)
    rec = watched(inc)
    tech, emp, admin = inc.assigned_technician, inc.reporter, make_admin()
    inc.add_note(tech, at(10), "Checked logs", NoteType.INVESTIGATION)
    inc.request_info(tech, at(11), "Which browser?")
    inc.respond_to_info(emp, at(12), "Chrome")
    inc.escalate(SYSTEM, at(13), EscalationDecision(EscalationLevel.TEAM_LEAD, None, "Slow"))
    inc.change_priority(admin, at(14), Priority.P2, "Lower impact", make_tracker(at(0)))
    inc.mark_possible_duplicate(SYSTEM, at(15), "INC-1001", 0.8)
    assert rec.types == [E.NOTE_ADDED, E.INFO_REQUESTED, E.INFO_RESPONDED, E.ESCALATED,
                         E.PRIORITY_CHANGED, E.DUPLICATE_FLAGGED]
    assert all(e.previous_status is S.IN_PROGRESS and e.new_status is S.IN_PROGRESS for e in rec.events)


def test_reassign_and_rejected_resolution_events():
    assigned = make_incident_in(S.ASSIGNED)
    rec = watched(assigned)
    assigned.reassign(make_admin(), at(5), make_technician(id=3, username="tech2"), 0)
    assert rec.types == [E.REASSIGNED]
    assert (rec.events[0].previous_status, rec.events[0].new_status) == (S.ASSIGNED, S.ASSIGNED)

    resolved = make_incident_in(S.RESOLVED)
    rec = watched(resolved)
    resolved.reject_resolution(resolved.reporter, at(10), "Still failing")
    assert rec.types == [E.RESOLUTION_REJECTED]
    assert (rec.events[0].previous_status, rec.events[0].new_status) == (S.RESOLVED, S.IN_PROGRESS)
    assert "Still failing" in rec.events[0].description and "Restarted DB pool" in rec.events[0].description


def test_event_descriptions_carry_the_useful_facts():
    inc = make_incident()
    rec = watched(inc)
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    inc.assign_to(SYSTEM, at(2), make_technician(), 0)
    classified, assigned = rec.events
    assert "Database" in classified.description and "P1" in classified.description and "3x3x3" in classified.description
    assert "Ravi K" in assigned.description and "tech1" in assigned.description


# ---- failed actions are silent --------------------------------------------------

def test_failed_actions_emit_nothing_and_leave_the_incident_untouched():
    inc = make_incident()
    rec = watched(inc)
    with pytest.raises(InvalidStateTransitionError):
        inc.close(inc.reporter, at(1))                                           # illegal in NEW
    with pytest.raises(UnauthorizedOperationError):
        inc.classify(inc.reporter, at(1), make_priority_result(), make_tracker())  # not the system
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    with pytest.raises(WorkloadExceededError):
        inc.assign_to(SYSTEM, at(2), make_technician(), 5)                       # workload
    with pytest.raises(InvalidInputError):
        inc.assign_to(SYSTEM, at(2), make_employee(), 0)                         # bad data
    assert rec.types == [E.CLASSIFIED]
    assert inc.status is S.CLASSIFIED and inc.assigned_technician is None


def test_observers_see_the_completed_change():
    inc = make_incident()
    rec = watched(inc)
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    inc.assign_to(SYSTEM, at(2), make_technician(), 0)
    assert rec.status_when_called == [e.new_status for e in rec.events] == [S.CLASSIFIED, S.ASSIGNED]


# ---- observer management --------------------------------------------------------

def test_observers_run_in_registration_order_and_are_never_added_twice():
    order = []

    class Named(IncidentObserver):
        def __init__(self, name):
            self.name = name

        def on_event(self, event):
            order.append(self.name)

    inc = make_incident()
    first, second = Named("first"), Named("second")
    inc.add_observer(first)
    inc.add_observer(second)
    inc.add_observer(first)                       # same object again: ignored
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    assert order == ["first", "second"]


def test_only_observers_can_be_attached():
    with pytest.raises(InvalidInputError):
        make_incident().add_observer(object())


def test_observers_are_not_carried_through_snapshot_and_restore():
    inc = make_incident_in(S.ASSIGNED)
    old = watched(inc)
    restored = Incident.restore(inc.snapshot())
    new = watched(restored)
    restored.acknowledge(restored.assigned_technician, at(10))
    assert new.types == [E.ACKNOWLEDGED] and old.events == []


def test_events_are_immutable():
    inc = make_incident()
    rec = watched(inc)
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.events[0].description = "tampered"


# ---- a failing observer must not break anything ----------------------------------

def test_failing_observer_does_not_undo_the_change_or_block_other_observers():
    logger = logging.getLogger("app.domain.models.incident")
    handler = ListHandler()
    logger.addHandler(handler)
    try:
        inc = make_incident()
        before, bomb, after = Recorder(), Exploding(RuntimeError("audit store down")), Recorder()
        for observer in (before, bomb, after):
            inc.add_observer(observer)
        inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())    # must not raise
    finally:
        logger.removeHandler(handler)

    assert inc.status is S.CLASSIFIED and inc.priority is Priority.P1          # change stands
    assert before.types == after.types == [E.CLASSIFIED]                       # others still ran
    assert bomb.calls == 1
    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.levelno == logging.ERROR and record.exc_info is not None
    assert "Exploding" in record.getMessage() and "CLASSIFIED" in record.getMessage()


def test_application_errors_from_observers_are_also_contained():
    inc = make_incident()
    bomb, rec = Exploding(PersistenceError("db locked")), Recorder()
    inc.add_observer(bomb)
    inc.add_observer(rec)
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    inc.assign_to(SYSTEM, at(2), make_technician(), 0)
    assert inc.status is S.ASSIGNED
    assert bomb.calls == 2 and rec.types == [E.CLASSIFIED, E.ASSIGNED]
