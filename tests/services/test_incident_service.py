"""P3 T5: the incident service, against the in-memory fakes."""
from datetime import timedelta

import pytest

from app.domain.enums import (
    IncidentEventType as E,
)
from app.domain.enums import (
    IncidentStatus as S,
)
from app.domain.enums import (
    Level,
    NoteType,
    Priority,
)
from app.domain.exceptions import (
    CategoryNotFoundError,
    DuplicateIncidentError,
    IncidentNotFoundError,
    InvalidInputError,
    InvalidStateTransitionError,
    MissingSlaConfigurationError,
    ServiceNotFoundError,
    TechnicianUnavailableError,
    UnauthorizedOperationError,
    UserNotFoundError,
    WorkloadExceededError,
)
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.user import Technician
from app.ports.dto import AuditFilter, IncidentSearchCriteria

from .helpers import T0, actions, at, create, finish, request, set_available

ADMINS = {"admin1", "admin2", "admin3"}


# ====================================================================================================
# Creating an incident
# ====================================================================================================

def test_creating_an_incident_classifies_prioritises_sets_the_sla_and_assigns(stack):
    w = stack.w
    incident = create(stack)
    assert (incident.ticket_number, incident.status, incident.priority, incident.priority_score) == \
           ("INC-1001", S.ASSIGNED, Priority.P1, 27)
    assert incident.assigned_technician.username == "tech1"                  # has the Database skill
    assert incident.sla_tracker.response_deadline == T0 + timedelta(minutes=5)
    assert incident.sla_tracker.resolution_deadline == T0 + timedelta(minutes=30)
    saved = stack.repos.incidents.find_by_id(incident.id)
    assert saved.status is S.ASSIGNED and saved.assigned_technician.id == w.tech.id      # final state was saved


def test_creating_an_incident_leaves_an_audit_trail_and_notifies_both_audiences(stack):
    incident = create(stack)
    assert actions(stack, incident) == ["CREATED", "CLASSIFIED", "ASSIGNED"]
    assert stack.rec.recipients_of(E.CREATED) == {"emp1"} | ADMINS
    assert stack.rec.recipients_of(E.ASSIGNED) == {"tech1", "emp1"}
    assert stack.rec.recipients_of(E.CLASSIFIED) == set()
    assert len(stack.repos.notifications.all()) == 6                           # 4 + 2, stored in-app too
    created = stack.repos.audits.find_by_incident(incident.id)[0]
    assert (created.actor_name, created.previous_status, created.new_status) == ("Asha Rao", None, S.NEW)


def test_a_service_without_its_own_policy_uses_the_default_and_with_one_uses_that(stack):
    w = stack.w
    strict = stack.repos.policies.save(SlaPolicy("Strict", False, {p: SlaTarget(3, 20) for p in Priority}))
    stack.repos.services.save(ITService("Payment", "Payments", Level.HIGH, strict.id, id=w.service.id))
    incident = create(stack)
    assert incident.sla_tracker.response_deadline == T0 + timedelta(minutes=3)
    assert incident.sla_tracker.resolution_deadline == T0 + timedelta(minutes=20)


def test_missing_sla_configuration_raises_and_creates_nothing(stack):
    stack.repos.policies._items.clear()                                          # no policy at all, no default
    with pytest.raises(MissingSlaConfigurationError):
        create(stack)
    assert stack.repos.incidents.all_incidents() == []                         # no half-created incident left behind
    assert stack.repos.audits.search(AuditFilter()) == []


def test_a_policy_without_a_target_for_the_priority_is_a_configuration_error(stack):
    stack.repos.policies._items.clear()
    only_p4 = stack.repos.policies.save(SlaPolicy("Partial", True, {Priority.P4: SlaTarget(240, 1440)}))
    with pytest.raises(MissingSlaConfigurationError):
        create(stack)
    assert only_p4.id and stack.repos.incidents.all_incidents() == []


@pytest.mark.parametrize("field,value", [
    ("title", "   "), ("title", "x" * 201), ("description", ""), ("affected_users", 0),
    ("affected_users", True), ("affected_users", "5"), ("impact", "HIGH"), ("urgency", None)])
def test_invalid_input_is_rejected_naming_the_field_and_nothing_is_saved(stack, field, value):
    with pytest.raises(InvalidInputError) as caught:
        stack.svc.create_incident(stack.w.reporter, request(stack.w, **{field: value}))
    assert caught.value.field == field
    assert stack.repos.incidents.all_incidents() == []


def test_unknown_or_inactive_services_and_categories_are_reported(stack):
    w = stack.w
    for bad in (999, None):
        with pytest.raises(ServiceNotFoundError):
            stack.svc.create_incident(w.reporter, request(w, service_id=bad))
        with pytest.raises(CategoryNotFoundError):
            stack.svc.create_incident(w.reporter, request(w, category_id=bad))
    stack.repos.services.save(ITService("Payment", "Payments", Level.HIGH, active=False, id=w.service.id))
    with pytest.raises(ServiceNotFoundError):
        stack.svc.create_incident(w.reporter, request(w))


def test_creating_needs_a_signed_in_active_user(stack):
    with pytest.raises(UnauthorizedOperationError):
        stack.svc.create_incident(None, request(stack.w))


def test_exact_resubmission_within_ten_minutes_is_rejected_then_allowed_later(stack):
    first = create(stack, "Payment down")
    stack.clock.advance(9)
    with pytest.raises(DuplicateIncidentError) as caught:
        create(stack, "  PAYMENT   down ")                                       # same title ignoring case and spacing
    assert first.ticket_number in caught.value.message
    stack.clock.advance(2)                                                       # now 11 minutes later
    assert create(stack, "Payment down").id != first.id
    assert len(stack.repos.incidents.all_incidents()) == 2


def test_the_same_title_from_another_person_or_on_another_service_is_not_a_resubmission(stack):
    w = stack.w
    create(stack, "Payment down")
    create(stack, "Payment down", actor=w.other_employee)                        # different reporter
    other_service = stack.repos.services.save(ITService("VPN", "", Level.LOW))
    create(stack, "Payment down", service_id=other_service.id)                   # different service
    assert len(stack.repos.incidents.all_incidents()) == 3


# ---- duplicate detection ----------------------------------------------------------------------------------

def test_a_similar_report_on_the_same_service_is_flagged_but_still_created(stack):
    w = stack.w
    first = create(stack, "Payment application unavailable")
    second = create(stack, "Payment transaction failing", actor=w.other_employee)
    third = create(stack, "Printer out of paper", actor=w.other_employee,
                   description="The office printer on floor 3 has no paper")
    assert second.possible_duplicate_of == first.ticket_number and first.possible_duplicate_of is None
    assert third.possible_duplicate_of is None
    assert "DUPLICATE_FLAGGED" in actions(stack, second) and "DUPLICATE_FLAGGED" not in actions(stack, third)
    assert stack.rec.recipients_of(E.DUPLICATE_FLAGGED) == ADMINS
    assert second.status is not S.NEW                                            # flag only: processing went on


def test_old_or_closed_incidents_are_not_duplicate_candidates(stack):
    first = create(stack, "Payment application unavailable")
    finish(stack, first)                                                         # CLOSED
    still_open = create(stack, "Payment transaction failing", actor=stack.w.other_employee)
    assert still_open.possible_duplicate_of is None
    stack.clock.advance(60 * 25)                                                 # 25 hours later
    old = create(stack, "Payment application unavailable", actor=stack.w.other_employee)
    assert old.possible_duplicate_of is None


# ---- assignment during creation -------------------------------------------------------------------------------

def test_with_nobody_available_the_incident_stays_classified_without_an_error(stack):
    for tech in (stack.w.tech, stack.w.tech2):
        set_available(stack, tech, False)
    incident = create(stack)
    assert incident.status is S.CLASSIFIED and incident.assigned_technician is None
    assert actions(stack, incident) == ["CREATED", "CLASSIFIED"]
    assert [i.ticket_number for i in stack.svc.search(stack.w.admin, IncidentSearchCriteria(status=S.CLASSIFIED))] == ["INC-1001"]


def test_skill_based_assignment_falls_back_to_load_based_when_nobody_has_the_skill_free(stack):
    set_available(stack, stack.w.tech, False)                                    # the only Database technician
    incident = create(stack)
    assert incident.assigned_technician.username == "tech2"                      # no skill, but free


def test_switching_the_assignment_strategy_changes_the_next_assignment_without_a_restart(stack):
    for n in range(2):                                                           # tech1 now has 2 active, tech2 none
        assert create(stack, f"Earlier issue {n}").assigned_technician.username == "tech1"
    assert create(stack, "Skill based third").assigned_technician.username == "tech1"
    stack.assignments.set_active("load_based")
    assert create(stack, "Load based fourth").assigned_technician.username == "tech2"
    stack.assignments.set_active("skill_based")
    assert create(stack, "Skill based again").assigned_technician.username == "tech1"


def test_switching_the_priority_strategy_changes_the_next_priority(stack):
    weighted = create(stack, "Weighted one", urgency=Level.LOW, affected_users=10)
    stack.priorities.set_active("rule_based")
    rule = create(stack, "Rule based one", urgency=Level.LOW, affected_users=10)
    assert (weighted.priority, rule.priority) == (Priority.P2, Priority.P1)      # HIGH criticality and HIGH impact: always P1


def test_a_full_technician_is_skipped(stack):
    w = stack.w
    busy = stack.repos.users.save(Technician("busy", "Busy B", "b@x.com", "h", {"Database"}, 9, True, 1))
    stack.repos.users.save(Technician("tech1", w.tech.full_name, w.tech.email, w.tech.password_hash,
                                      {"Database"}, 4, False, 5, id=w.tech.id))     # tech1 unavailable
    first, second = create(stack, "First"), create(stack, "Second")
    assert first.assigned_technician.id == busy.id                               # takes its single slot
    assert second.assigned_technician.username == "tech2"                        # busy is full, tech1 away


# ====================================================================================================
# Manual and automatic assignment by an administrator
# ====================================================================================================

def test_auto_assign_works_once_someone_is_free_and_fails_clearly_before(stack):
    w = stack.w
    for tech in (w.tech, w.tech2):
        set_available(stack, tech, False)
    incident = create(stack)
    with pytest.raises(TechnicianUnavailableError):
        stack.svc.auto_assign(w.admin, incident.id)
    set_available(stack, w.tech, True)
    assigned = stack.svc.auto_assign(w.admin, incident.id)
    assert assigned.status is S.ASSIGNED and assigned.assigned_technician.username == "tech1"
    assert stack.repos.audits.find_by_incident(incident.id)[-1].actor_name == "Meera N"      # the admin did it
    with pytest.raises(InvalidStateTransitionError):
        stack.svc.auto_assign(w.admin, incident.id)                              # already assigned
    with pytest.raises(UnauthorizedOperationError):
        stack.svc.auto_assign(w.reporter, incident.id)


def test_an_administrator_assigns_and_then_reassigns(stack):
    w = stack.w
    for tech in (w.tech, w.tech2):
        set_available(stack, tech, False)
    incident = create(stack)
    set_available(stack, w.tech, True)
    set_available(stack, w.tech2, True)
    assert stack.svc.assign(w.admin, incident.id, w.tech2.id).assigned_technician.username == "tech2"
    moved = stack.svc.assign(w.admin, incident.id, w.tech.id)
    assert moved.assigned_technician.username == "tech1" and moved.status is S.ASSIGNED
    assert actions(stack, incident)[-2:] == ["ASSIGNED", "REASSIGNED"]
    assert stack.rec.recipients_of(E.REASSIGNED) == {"tech1", "emp1"}
    assert stack.repos.incidents.find_by_id(incident.id).assigned_technician.username == "tech1"


def test_assignment_targets_are_checked(stack):
    w = stack.w
    set_available(stack, w.tech, False)
    set_available(stack, w.tech2, False)
    incident = create(stack)
    with pytest.raises(UserNotFoundError):
        stack.svc.assign(w.admin, incident.id, 999)
    with pytest.raises(InvalidInputError):
        stack.svc.assign(w.admin, incident.id, w.reporter.id)                     # not a technician
    with pytest.raises(TechnicianUnavailableError):
        stack.svc.assign(w.admin, incident.id, w.tech.id)                        # on leave
    gone = stack.repos.users.find_by_id(w.tech2.id)
    gone.deactivate()
    stack.repos.users.save(gone)
    with pytest.raises(TechnicianUnavailableError):
        stack.svc.assign(w.admin, incident.id, w.tech2.id)                       # deactivated
    for actor in (w.reporter, w.tech):
        with pytest.raises(UnauthorizedOperationError):
            stack.svc.assign(actor, incident.id, w.tech.id)


def test_assigning_to_a_technician_at_the_workload_limit_is_refused(stack):
    w = stack.w
    tiny = stack.repos.users.save(Technician("tiny", "Tiny T", "t@x.com", "h", {"Network"}, 1, True, 1))
    for tech in (w.tech, w.tech2):
        set_available(stack, tech, False)
    first, second = create(stack, "One"), create(stack, "Two")                    # tiny takes one, none left for two
    assert first.assigned_technician.id == tiny.id and second.status is S.CLASSIFIED
    with pytest.raises(WorkloadExceededError):
        stack.svc.assign(w.admin, second.id, tiny.id)


def test_recommendations_are_ranked_with_reasons_and_for_administrators_only(stack):
    w = stack.w
    incident = create(stack)
    ranked = stack.svc.recommend_technicians(w.admin, incident.id)
    assert [r.technician.username for r in ranked] == ["tech1", "tech2"]
    assert ranked[0].score > ranked[1].score and "has skill Database" in ranked[0].reasons
    with pytest.raises(UnauthorizedOperationError):
        stack.svc.recommend_technicians(w.reporter, incident.id)


# ====================================================================================================
# The lifecycle, step by step
# ====================================================================================================

def test_full_happy_path_through_the_service_with_audit_and_notifications_at_every_step(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    stack.clock.advance(3)
    s.acknowledge(w.tech, incident.id)
    s.start_investigation(w.tech, incident.id)
    s.add_note(w.tech, incident.id, "Checking the connection pool")
    s.request_info(w.tech, incident.id, "Which app version?")
    s.respond_to_info_request(w.reporter, incident.id, "Version 2.3")
    s.resolve(w.tech, incident.id, "Restarted pool", "The pool was exhausted")
    s.verify(w.reporter, incident.id)
    s.close(w.reporter, incident.id)
    done = s.submit_feedback(w.reporter, incident.id, 5, "Fast fix")
    assert done.status is S.CLOSED and done.feedback.rating == 5 and done.resolution.summary == "Restarted pool"
    assert actions(stack, incident) == [
        "CREATED", "CLASSIFIED", "ASSIGNED", "ACKNOWLEDGED", "INVESTIGATION_STARTED", "NOTE_ADDED",
        "INFO_REQUESTED", "INFO_RESPONDED", "RESOLVED", "VERIFIED", "CLOSED", "FEEDBACK_SUBMITTED"]
    assert stack.rec.recipients_of(E.RESOLVED) == {"emp1"} and stack.rec.recipients_of(E.CLOSED) == {"emp1", "tech1"}
    reloaded = stack.repos.incidents.find_by_id(incident.id)
    assert reloaded.status is S.CLOSED
    assert [n.note_type for n in reloaded.notes] == [NoteType.INVESTIGATION, NoteType.INFO_REQUEST,
                                                     NoteType.INFO_RESPONSE]


def test_every_action_stamps_the_injected_clock(stack):
    w = stack.w
    incident = create(stack)
    stack.clock.advance(30)
    stack.svc.acknowledge(w.tech, incident.id)
    ack = next(r for r in stack.repos.audits.find_by_incident(incident.id) if r.action == "ACKNOWLEDGED")
    assert ack.timestamp == at(30) and stack.repos.incidents.find_by_id(incident.id).acknowledged_at == at(30)


def test_the_reporter_can_add_information_and_the_technician_an_investigation_note(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    s.acknowledge(w.tech, incident.id)
    s.start_investigation(w.tech, incident.id)
    s.add_note(w.reporter, incident.id, "It also fails on mobile")
    s.add_note(w.tech, incident.id, "Reproduced it")
    kinds = [n.note_type for n in stack.repos.incidents.find_by_id(incident.id).notes]
    assert kinds == [NoteType.INFO_RESPONSE, NoteType.INVESTIGATION]
    with pytest.raises(UnauthorizedOperationError):
        s.add_note(w.other_employee, incident.id, "Me too")


def test_a_rejected_resolution_returns_the_incident_to_in_progress(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    s.acknowledge(w.tech, incident.id)
    s.start_investigation(w.tech, incident.id)
    s.resolve(w.tech, incident.id, "Tried a fix", "Details")
    back = s.reject_resolution(w.reporter, incident.id, "Still failing")
    assert back.status is S.IN_PROGRESS and back.resolution is None
    assert stack.rec.recipients_of(E.RESOLUTION_REJECTED) == {"tech1"}


def test_illegal_transitions_and_wrong_actors_are_refused_by_the_domain(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)                                                     # ASSIGNED
    with pytest.raises(InvalidStateTransitionError):
        s.close(w.reporter, incident.id)                                         # cannot jump to CLOSED
    with pytest.raises(InvalidStateTransitionError):
        s.resolve(w.tech, incident.id, "x", "y")
    with pytest.raises(UnauthorizedOperationError):
        s.acknowledge(w.reporter, incident.id)                                   # the reporter is not the technician
    with pytest.raises(UnauthorizedOperationError):
        s.acknowledge(w.tech2, incident.id)                                      # a different technician
    assert stack.repos.incidents.find_by_id(incident.id).status is S.ASSIGNED   # nothing changed


def test_invalid_data_for_an_action_is_an_input_error_and_changes_nothing(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    s.acknowledge(w.tech, incident.id)
    s.start_investigation(w.tech, incident.id)
    with pytest.raises(InvalidInputError):
        s.resolve(w.tech, incident.id, "  ", "details")
    with pytest.raises(InvalidInputError):
        s.add_note(w.tech, incident.id, "x" * 4001)
    assert stack.repos.incidents.find_by_id(incident.id).status is S.IN_PROGRESS


def test_feedback_needs_the_reporter_a_valid_rating_and_a_finished_incident(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    with pytest.raises(InvalidStateTransitionError):
        s.submit_feedback(w.reporter, incident.id, 5, "too early")
    finish(stack, incident)
    for bad in (0, 6):
        with pytest.raises(InvalidInputError):
            s.submit_feedback(w.reporter, incident.id, bad, "")
    with pytest.raises(UnauthorizedOperationError):
        s.submit_feedback(w.admin, incident.id, 5, "not mine")


# ====================================================================================================
# Reading, searching and authorization
# ====================================================================================================

def test_an_employee_cannot_read_another_employees_incident(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)                                                     # reported by emp1, assigned to tech1
    for allowed in (w.reporter, w.tech, w.admin):
        assert s.get_incident(allowed, incident.id).ticket_number == "INC-1001"
    for denied in (w.other_employee, w.tech2):
        with pytest.raises(UnauthorizedOperationError):
            s.get_incident(denied, incident.id)
        with pytest.raises(UnauthorizedOperationError):
            s.get_audit_trail(denied, incident.id)
    assert [r.action for r in s.get_audit_trail(w.reporter, incident.id)][0] == "CREATED"


def test_unknown_incident_ids_are_reported(stack):
    for bad in (999, None, "1"):
        with pytest.raises(IncidentNotFoundError):
            stack.svc.get_incident(stack.w.admin, bad)
        with pytest.raises(IncidentNotFoundError):
            stack.svc.acknowledge(stack.w.tech, bad)


def test_a_user_who_cannot_see_the_incident_cannot_act_on_it(stack):
    incident = create(stack)
    with pytest.raises(UnauthorizedOperationError):
        stack.svc.add_note(stack.w.other_employee, incident.id, "hello")
    assert stack.repos.incidents.find_by_id(incident.id).notes == []


def test_search_is_scoped_by_role(stack):
    w, s = stack.w, stack.svc
    mine = create(stack, "Mine one")
    create(stack, "Mine two")
    theirs = create(stack, "Theirs one", actor=w.other_employee)
    set_available(stack, w.tech, False)
    set_available(stack, w.tech2, False)
    unassigned = create(stack, "Nobody has it")
    everything = IncidentSearchCriteria()
    assert {i.title for i in s.search(w.reporter, everything)} == {"Mine one", "Mine two", "Nobody has it"}
    assert {i.title for i in s.search(w.other_employee, everything)} == {"Theirs one"}
    assert {i.title for i in s.search(w.tech, everything)} == {"Mine one", "Mine two", "Theirs one"}
    assert {i.title for i in s.search(w.tech2, everything)} == set()
    assert len(s.search(w.admin, everything)) == 4
    snooping = IncidentSearchCriteria(reporter_id=w.other_employee.id)
    assert {i.title for i in s.search(w.reporter, snooping)} == {"Mine one", "Mine two", "Nobody has it"}
    assert [i.id for i in s.search(w.admin, IncidentSearchCriteria(keyword="theirs"))] == [theirs.id]
    assert mine.id and unassigned.id


# ====================================================================================================
# Priority override
# ====================================================================================================

def test_overriding_the_priority_recalculates_the_deadlines_and_tells_the_right_people(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)                                                     # P1: 5 and 30 minutes
    stack.clock.advance(10)                                                      # time has passed since creation
    changed = s.override_priority(w.admin, incident.id, Priority.P3, "Only affects reports")
    assert changed.priority is Priority.P3
    assert changed.sla_tracker.response_deadline == T0 + timedelta(minutes=60)   # counted from creation
    assert changed.sla_tracker.resolution_deadline == T0 + timedelta(minutes=480)
    assert stack.repos.incidents.find_by_id(incident.id).priority is Priority.P3
    assert "PRIORITY_CHANGED" in actions(stack, incident)
    assert stack.rec.recipients_of(E.PRIORITY_CHANGED) == {"tech1", "emp1"}


def test_priority_override_is_restricted_and_validated(stack):
    w, s = stack.w, stack.svc
    incident = create(stack)
    for actor in (w.reporter, w.tech):
        with pytest.raises(UnauthorizedOperationError):
            s.override_priority(actor, incident.id, Priority.P3, "no")
    with pytest.raises(InvalidInputError):
        s.override_priority(w.admin, incident.id, Priority.P1, "same as now")
    with pytest.raises(InvalidInputError):
        s.override_priority(w.admin, incident.id, "P3", "wrong type")
    with pytest.raises(InvalidInputError):
        s.override_priority(w.admin, incident.id, Priority.P2, "   ")
    assert stack.repos.incidents.find_by_id(incident.id).priority is Priority.P1

