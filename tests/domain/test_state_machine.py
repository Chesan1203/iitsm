import pytest

from app.domain.enums import (
    EscalationLevel, IncidentStatus as S, NoteType, Priority,
)
from app.domain.exceptions import (
    InvalidInputError, InvalidStateTransitionError, TechnicianUnavailableError,
    UnauthorizedOperationError, WorkloadExceededError,
)
from app.domain.intelligence.escalation_policy import EscalationDecision
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.domain.state import states
from app.domain.state.incident_state import IncidentState
from app.domain.state.state_factory import IncidentStateFactory
from tests.domain.helpers import (
    at, make_admin, make_employee, make_incident, make_incident_in, make_priority_result,
    make_technician, make_tracker,
)

SYSTEM = User.system()
ACTIONS = ["record_creation", "classify", "assign_to", "reassign", "acknowledge",
           "start_investigation", "add_note", "request_info", "respond_to_info", "resolve",
           "verify", "reject_resolution", "close", "submit_feedback", "escalate",
           "change_priority", "mark_possible_duplicate", "apply_sla_result"]
OPEN_COMMON = {"add_note", "escalate", "change_priority", "mark_possible_duplicate",
               "apply_sla_result"}

# The lifecycle table of the plan (5.8), as data: which actions each state overrides.
LEGAL = {
    states.NewState: OPEN_COMMON | {"record_creation", "classify"},
    states.ClassifiedState: OPEN_COMMON | {"assign_to"},
    states.AssignedState: OPEN_COMMON | {"reassign", "acknowledge"},
    states.AcknowledgedState: OPEN_COMMON | {"start_investigation"},
    states.InProgressState: OPEN_COMMON | {"request_info", "respond_to_info", "resolve"},
    states.ResolvedState: OPEN_COMMON | {"verify", "reject_resolution"},
    states.VerifiedState: OPEN_COMMON | {"close", "submit_feedback"},
    states.ClosedState: {"submit_feedback"},
}


def classified_incident():
    inc = make_incident()
    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    return inc


# ---- the lifecycle -----------------------------------------------------------

def test_full_happy_path_through_every_status():
    inc, emp, tech = make_incident(), None, make_technician()
    emp = inc.reporter
    inc.record_creation(emp, at(0))
    assert inc.status is S.NEW

    inc.classify(SYSTEM, at(1), make_priority_result(), make_tracker())
    assert (inc.status, inc.priority, inc.priority_score) == (S.CLASSIFIED, Priority.P1, 27)
    assert inc.sla_tracker is not None

    inc.assign_to(SYSTEM, at(2), tech, 0)
    assert (inc.status, inc.assigned_technician, inc.assigned_at) == (S.ASSIGNED, tech, at(2))
    assert inc.is_active

    inc.acknowledge(tech, at(3))
    assert (inc.status, inc.acknowledged_at) == (S.ACKNOWLEDGED, at(3))

    inc.start_investigation(tech, at(4))
    assert inc.status is S.IN_PROGRESS

    inc.resolve(tech, at(5), "Restarted DB pool", "Pool was exhausted")
    assert (inc.status, inc.resolved_at, inc.resolution.summary) == (S.RESOLVED, at(5), "Restarted DB pool")
    assert inc.resolution.resolved_by == tech

    inc.verify(emp, at(6))
    assert (inc.status, inc.verified_at) == (S.VERIFIED, at(6))

    inc.close(emp, at(7))
    assert (inc.status, inc.closed_at) == (S.CLOSED, at(7))
    assert not inc.is_open and not inc.is_active

    inc.submit_feedback(emp, at(8), 5, "Fast fix")
    assert inc.feedback.rating == 5


def test_new_to_closed_is_impossible():
    inc = make_incident()
    with pytest.raises(InvalidStateTransitionError) as e:
        inc.close(inc.reporter, at(1))
    assert str(e.value) == "Cannot close an incident that is NEW"
    assert inc.status is S.NEW and inc.closed_at is None


def test_transition_table_matches_the_plan():
    for state_class, legal in LEGAL.items():
        overridden = {a for a in ACTIONS if getattr(state_class, a) is not getattr(IncidentState, a)}
        assert overridden == legal, state_class.__name__


def test_factory_maps_every_status_to_its_own_shared_state():
    for status in S:
        state = IncidentStateFactory.for_status(status)
        assert state.status is status
        assert IncidentStateFactory.for_status(status) is state
    with pytest.raises(InvalidInputError):
        IncidentStateFactory.for_status("NEW")


def test_state_is_derived_from_status_after_restore():
    inc = make_incident_in(S.RESOLVED)
    with pytest.raises(InvalidStateTransitionError):
        inc.acknowledge(inc.assigned_technician, at(10))
    inc.verify(inc.reporter, at(10))
    assert inc.status is S.VERIFIED


def test_restored_in_progress_incident_can_be_resolved():
    inc = make_incident_in(S.IN_PROGRESS)
    inc.resolve(inc.assigned_technician, at(9), "Fixed", "Details")
    assert inc.status is S.RESOLVED


# ---- order of checks ----------------------------------------------------------

def test_illegal_state_is_reported_before_missing_permission():
    inc = make_incident()
    stranger = make_employee(id=99, username="other")
    with pytest.raises(InvalidStateTransitionError):
        inc.close(stranger, at(1))


def test_missing_permission_is_reported_before_invalid_data():
    inc = make_incident_in(S.IN_PROGRESS)
    with pytest.raises(UnauthorizedOperationError):
        inc.resolve(make_employee(), at(9), "", "")
    with pytest.raises(InvalidInputError):
        inc.resolve(inc.assigned_technician, at(9), "", "")


# ---- classify / assign / reassign ---------------------------------------------

def test_only_the_system_can_classify():
    for actor in (make_admin(), make_employee(), make_technician()):
        inc = make_incident()
        with pytest.raises(UnauthorizedOperationError):
            inc.classify(actor, at(1), make_priority_result(), make_tracker())
        assert inc.status is S.NEW


def test_classify_validates_its_inputs():
    inc = make_incident()
    with pytest.raises(InvalidInputError):
        inc.classify(SYSTEM, at(1), "P1", make_tracker())
    with pytest.raises(InvalidInputError):
        inc.classify(SYSTEM, at(1), make_priority_result(), None)


def test_assignment_permissions():
    for actor in (make_employee(), make_technician()):
        inc = classified_incident()
        with pytest.raises(UnauthorizedOperationError):
            inc.assign_to(actor, at(2), make_technician(), 0)
    for actor in (SYSTEM, make_admin()):
        inc = classified_incident()
        inc.assign_to(actor, at(2), make_technician(), 0)
        assert inc.status is S.ASSIGNED


def test_unavailable_or_inactive_technician_cannot_be_assigned():
    for tech in (make_technician(available=False), make_technician(active=False)):
        inc = classified_incident()
        with pytest.raises(TechnicianUnavailableError):
            inc.assign_to(SYSTEM, at(2), tech, 0)
        assert inc.status is S.CLASSIFIED and inc.assigned_technician is None


def test_workload_limit_is_enforced_at_the_boundary():
    inc = classified_incident()
    with pytest.raises(WorkloadExceededError):
        inc.assign_to(SYSTEM, at(2), make_technician(), 5)
    inc.assign_to(SYSTEM, at(2), make_technician(), 4)
    assert inc.status is S.ASSIGNED
    small = make_technician(id=3, username="tech2", max_workload=1)
    other = classified_incident()
    with pytest.raises(WorkloadExceededError):
        other.assign_to(SYSTEM, at(2), small, 1)


def test_assign_rejects_bad_data():
    inc = classified_incident()
    with pytest.raises(InvalidInputError):
        inc.assign_to(SYSTEM, at(2), make_employee(), 0)
    with pytest.raises(InvalidInputError):
        inc.assign_to(SYSTEM, at(2), make_technician(), -1)


def test_reassign_by_admin_only_and_to_a_different_technician():
    new_tech = make_technician(id=3, username="tech2")
    for actor in (SYSTEM, make_employee(), make_technician()):
        inc = make_incident_in(S.ASSIGNED)
        with pytest.raises(UnauthorizedOperationError):
            inc.reassign(actor, at(4), new_tech, 0)
    inc = make_incident_in(S.ASSIGNED)
    with pytest.raises(InvalidInputError):
        inc.reassign(make_admin(), at(4), make_technician(), 0)
    inc.reassign(make_admin(), at(4), new_tech, 0)
    assert (inc.status, inc.assigned_technician, inc.assigned_at) == (S.ASSIGNED, new_tech, at(4))
    full = make_technician(id=4, username="tech3")
    with pytest.raises(WorkloadExceededError):
        inc.reassign(make_admin(), at(5), full, 5)


# ---- technician actions -------------------------------------------------------

def test_only_the_assigned_technician_can_acknowledge():
    for actor in (make_employee(), make_admin(), SYSTEM, make_technician(id=3, username="tech2")):
        inc = make_incident_in(S.ASSIGNED)
        with pytest.raises(UnauthorizedOperationError):
            inc.acknowledge(actor, at(4))
        assert inc.status is S.ASSIGNED
    inc = make_incident_in(S.ASSIGNED)
    inc.acknowledge(inc.assigned_technician, at(4))
    assert inc.status is S.ACKNOWLEDGED


def test_start_investigation_needs_acknowledgement_first():
    inc = make_incident_in(S.ASSIGNED)
    with pytest.raises(InvalidStateTransitionError):
        inc.start_investigation(inc.assigned_technician, at(4))
    inc = make_incident_in(S.ACKNOWLEDGED)
    with pytest.raises(UnauthorizedOperationError):
        inc.start_investigation(inc.reporter, at(4))
    inc.start_investigation(inc.assigned_technician, at(4))
    assert inc.status is S.IN_PROGRESS


def test_resolve_requires_in_progress_and_valid_text():
    inc = make_incident_in(S.ACKNOWLEDGED)
    with pytest.raises(InvalidStateTransitionError):
        inc.resolve(inc.assigned_technician, at(9), "Fixed", "d")
    inc = make_incident_in(S.IN_PROGRESS)
    with pytest.raises(InvalidInputError) as e:
        inc.resolve(inc.assigned_technician, at(9), "  ", "d")
    assert e.value.field == "summary"
    assert inc.status is S.IN_PROGRESS and inc.resolution is None


# ---- information request cycle ------------------------------------------------

def test_information_request_and_response_cycle():
    inc = make_incident_in(S.IN_PROGRESS)
    tech, emp = inc.assigned_technician, inc.reporter
    assert not inc.has_pending_info_request
    with pytest.raises(InvalidStateTransitionError):
        inc.respond_to_info(emp, at(5), "no question asked yet")

    inc.request_info(tech, at(5), "Which browser?")
    assert inc.has_pending_info_request
    assert inc.notes[-1].note_type is NoteType.INFO_REQUEST and inc.status is S.IN_PROGRESS
    with pytest.raises(UnauthorizedOperationError):
        inc.respond_to_info(make_employee(id=99, username="other"), at(6), "x")
    with pytest.raises(UnauthorizedOperationError):
        inc.request_info(emp, at(6), "reporter cannot ask")

    inc.respond_to_info(emp, at(7), "Chrome 120")
    assert not inc.has_pending_info_request
    assert inc.notes[-1].note_type is NoteType.INFO_RESPONSE and inc.notes[-1].author == emp
    with pytest.raises(InvalidStateTransitionError):
        inc.respond_to_info(emp, at(8), "answering twice")


def test_investigation_notes_do_not_clear_a_pending_question():
    inc = make_incident_in(S.IN_PROGRESS)
    inc.request_info(inc.assigned_technician, at(5), "Which browser?")
    inc.add_note(inc.assigned_technician, at(6), "Checking logs meanwhile", NoteType.INVESTIGATION)
    assert inc.has_pending_info_request


def test_add_note_rules():
    inc = make_incident_in(S.IN_PROGRESS)
    tech, emp = inc.assigned_technician, inc.reporter
    inc.add_note(tech, at(5), "Checked DB logs", NoteType.INVESTIGATION)
    inc.add_note(emp, at(6), "It also fails on mobile", NoteType.INFO_RESPONSE)
    assert [n.note_type for n in inc.notes] == [NoteType.INVESTIGATION, NoteType.INFO_RESPONSE]
    with pytest.raises(UnauthorizedOperationError):
        inc.add_note(emp, at(7), "reporter posing as technician", NoteType.INVESTIGATION)
    with pytest.raises(UnauthorizedOperationError):
        inc.add_note(tech, at(7), "technician posing as reporter", NoteType.INFO_RESPONSE)
    with pytest.raises(InvalidInputError):
        inc.add_note(tech, at(7), "question", NoteType.INFO_REQUEST)
    with pytest.raises(InvalidInputError):
        inc.add_note(tech, at(7), "   ", NoteType.INVESTIGATION)
    assert len(inc.notes) == 2


def test_note_legality_depends_on_state():
    new = make_incident()
    new.add_note(new.reporter, at(1), "Extra detail", NoteType.INFO_RESPONSE)       # reporter: any open state
    with pytest.raises(InvalidStateTransitionError):
        new.add_note(make_technician(), at(1), "too early", NoteType.INVESTIGATION)  # nobody assigned yet
    closed = make_incident_in(S.CLOSED)
    with pytest.raises(InvalidStateTransitionError):
        closed.add_note(closed.reporter, at(20), "too late", NoteType.INFO_RESPONSE)
    verified = make_incident_in(S.VERIFIED)
    with pytest.raises(InvalidStateTransitionError):
        verified.add_note(verified.assigned_technician, at(20), "after verify", NoteType.INVESTIGATION)


# ---- verify / reject / close / feedback ---------------------------------------

def test_verify_and_close_permissions():
    for actor_factory in (lambda i: i.assigned_technician, lambda i: make_employee(id=99, username="o"), lambda i: SYSTEM):
        inc = make_incident_in(S.RESOLVED)
        with pytest.raises(UnauthorizedOperationError):
            inc.verify(actor_factory(inc), at(10))
        inc = make_incident_in(S.VERIFIED)
        with pytest.raises(UnauthorizedOperationError):
            inc.close(actor_factory(inc), at(10))
    inc = make_incident_in(S.RESOLVED)
    inc.verify(make_admin(), at(10))
    inc.close(make_admin(), at(11))
    assert inc.status is S.CLOSED


def test_rejecting_a_resolution_reopens_the_incident():
    inc = make_incident_in(S.RESOLVED)
    tech, emp = inc.assigned_technician, inc.reporter
    with pytest.raises(UnauthorizedOperationError):
        inc.reject_resolution(make_admin(), at(10), "not fixed")
    with pytest.raises(InvalidInputError):
        inc.reject_resolution(emp, at(10), " ")
    inc.reject_resolution(emp, at(10), "Still failing")
    assert inc.status is S.IN_PROGRESS and inc.resolved_at is None and inc.resolution is None
    inc.resolve(tech, at(12), "Real fix", "Replaced the faulty node")
    assert inc.status is S.RESOLVED and inc.resolved_at == at(12)


def test_feedback_rules():
    early = make_incident_in(S.RESOLVED)
    with pytest.raises(InvalidStateTransitionError):
        early.submit_feedback(early.reporter, at(10), 4, "too soon")
    for status in (S.VERIFIED, S.CLOSED):
        inc = make_incident_in(status)
        with pytest.raises(UnauthorizedOperationError):
            inc.submit_feedback(make_employee(id=99, username="o"), at(10), 4, "")
        with pytest.raises(InvalidInputError):
            inc.submit_feedback(inc.reporter, at(10), 6, "")
        assert inc.feedback is None
        inc.submit_feedback(inc.reporter, at(10), 4, "Good")
        assert inc.feedback.rating == 4
        with pytest.raises(InvalidStateTransitionError):
            inc.submit_feedback(inc.reporter, at(11), 5, "again")


def test_closed_incident_accepts_nothing_else():
    inc = make_incident_in(S.CLOSED)
    admin = make_admin()
    for call in (lambda: inc.close(admin, at(20)),
                 lambda: inc.escalate(admin, at(20), EscalationDecision(EscalationLevel.TEAM_LEAD, None, "x")),
                 lambda: inc.change_priority(admin, at(20), Priority.P2, "why", make_tracker()),
                 lambda: inc.mark_possible_duplicate(admin, at(20), "INC-1", 0.9),
                 lambda: inc.reassign(admin, at(20), make_technician(id=3, username="t"), 0)):
        with pytest.raises(InvalidStateTransitionError):
            call()


# ---- creation, escalation, priority, duplicates --------------------------------

def test_record_creation_by_reporter_or_system_while_new_only():
    for actor in (make_incident().reporter, SYSTEM):
        inc = make_incident()
        inc.record_creation(actor, at(0))
        assert inc.status is S.NEW
    inc = make_incident()
    with pytest.raises(UnauthorizedOperationError):
        inc.record_creation(make_employee(id=99, username="o"), at(0))
    with pytest.raises(InvalidStateTransitionError):
        classified_incident().record_creation(SYSTEM, at(2))


def test_escalation_raises_the_level_and_never_lowers_it():
    inc = make_incident_in(S.ASSIGNED)
    up = EscalationDecision(EscalationLevel.TEAM_LEAD, None, "No acknowledgement")
    with pytest.raises(UnauthorizedOperationError):
        inc.escalate(make_technician(), at(10), up)
    inc.escalate(SYSTEM, at(10), up)
    assert inc.escalation_level is EscalationLevel.TEAM_LEAD
    with pytest.raises(InvalidInputError):
        inc.escalate(SYSTEM, at(11), up)
    inc.escalate(make_admin(), at(20), EscalationDecision(EscalationLevel.IT_MANAGER, None, "Still open"))
    assert inc.escalation_level is EscalationLevel.IT_MANAGER
    with pytest.raises(InvalidInputError):
        inc.escalate(SYSTEM, at(30), EscalationDecision(EscalationLevel.SYSTEM_ADMIN, None, "backwards"))


def test_change_priority_swaps_priority_and_sla_tracker():
    new = make_incident()
    with pytest.raises(InvalidStateTransitionError):
        new.change_priority(make_admin(), at(1), Priority.P2, "not classified yet", make_tracker())
    inc = make_incident_in(S.IN_PROGRESS)
    tracker = make_tracker(at(0))
    with pytest.raises(UnauthorizedOperationError):
        inc.change_priority(make_employee(), at(5), Priority.P2, "why", tracker)
    with pytest.raises(InvalidInputError):
        inc.change_priority(make_admin(), at(5), Priority.P2, "  ", tracker)
    with pytest.raises(InvalidInputError):
        inc.change_priority(make_admin(), at(5), Priority.P1, "same priority", tracker)
    inc.change_priority(make_admin(), at(5), Priority.P2, "Lower business impact", tracker)
    assert inc.priority is Priority.P2 and inc.priority_score == 27
    assert inc.sla_tracker is not tracker and inc.sla_tracker == tracker      # a private copy


def test_possible_duplicate_flagging():
    inc = make_incident()
    inc.assign_identity(7, "INC-1007")
    with pytest.raises(UnauthorizedOperationError):
        inc.mark_possible_duplicate(make_employee(), at(1), "INC-1001", 0.8)
    for bad_ticket, bad_score in (("INC-1007", 0.8), ("INC-1001", 1.5), ("INC-1001", -0.1), ("", 0.8)):
        with pytest.raises(InvalidInputError):
            inc.mark_possible_duplicate(SYSTEM, at(1), bad_ticket, bad_score)
    inc.mark_possible_duplicate(SYSTEM, at(1), "INC-1001", 0.77)
    assert inc.possible_duplicate_of == "INC-1001" and inc.status is S.NEW


def test_internal_setter_only_touches_whitelisted_fields():
    inc = make_incident()
    with pytest.raises(InvalidInputError):
        inc._set(title="hacked")
    with pytest.raises(InvalidInputError):
        inc._set(status=S.CLASSIFIED, reporter=None)
    assert inc.title == "Payment down" and inc.status is S.NEW      # all or nothing
