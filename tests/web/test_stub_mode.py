"""Web T1: stub mode (ITSM_MODE=stub). Every service method returns something sensible, the domain's
state and permission rules still apply, and incident 999 refuses everything."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.enums import AdminLevel, IncidentStatus as S, Level, Priority, Role, SlaStatus
from app.domain.exceptions import (
    IncidentNotFoundError, InvalidInputError, InvalidLoginError, InvalidStateTransitionError,
    TechnicianUnavailableError, UnauthorizedOperationError,
)
from app.main import create_app
from app.ports.container import Container
from app.ports.dto import (
    AuditFilter, CategoryRequest, CreateIncidentRequest, CreateUserRequest, IncidentSearchCriteria,
    RegisterRequest, ServiceRequest, SlaPolicyRequest,
)
from app.ports.services import (
    AdminService, AuthService, IncidentService, LookupService, NotificationService, ReportService,
)
from app.web.stubs.sample_data import ERROR_INCIDENT_ID, PASSWORD
from app.web.stubs.wiring import build_stub_container

TARGETS = {Priority.P1: (5, 30), Priority.P2: (15, 120), Priority.P3: (60, 480), Priority.P4: (240, 1440)}


@pytest.fixture
def stub() -> Container:
    return build_stub_container()


@pytest.fixture
def who(stub):
    """Named sample users, as the login would return them."""
    return {name: stub.auth.login(name, PASSWORD) for name in
            ("emp1", "emp2", "emp3", "tech1", "tech2", "tech3", "admin1", "admin2", "admin3")}


# ---- the container -----------------------------------------------------------------------------------------

def test_the_stub_container_has_all_six_services_of_the_right_type(stub):
    for attribute, interface in (("auth", AuthService), ("incidents", IncidentService), ("lookup", LookupService),
                                 ("admin", AdminService), ("reports", ReportService), ("notifications", NotificationService)):
        assert isinstance(getattr(stub, attribute), interface), attribute


def test_each_start_gets_fresh_data_and_changes_are_not_shared(stub, who):
    stub.admin.set_assignment_strategy(who["admin1"], "load_based")
    other = build_stub_container()
    admin = other.auth.login("admin1", PASSWORD)
    assert other.admin.get_assignment_strategy(admin) == "skill_based"


# ---- authentication ------------------------------------------------------------------------------------------

def test_login_register_and_get_user(stub):
    assert stub.auth.login("emp1", PASSWORD).role is Role.EMPLOYEE
    for username, password in (("emp1", "wrong"), ("nobody", PASSWORD)):
        with pytest.raises(InvalidLoginError):
            stub.auth.login(username, password)
    created = stub.auth.register_employee(RegisterRequest("new.user", "New User", "n@x.com", PASSWORD, "Ops"))
    assert created.id and stub.auth.get_user(created.id).username == "new.user" and stub.auth.get_user(999) is None
    for bad in (RegisterRequest("", "N", "n@x.com", PASSWORD), RegisterRequest("u", "N", "no-at", PASSWORD),
                RegisterRequest("u", "N", "n@x.com", "short"), RegisterRequest("emp1", "N", "n@x.com", PASSWORD)):
        with pytest.raises(InvalidInputError):
            stub.auth.register_employee(bad)


# ---- incidents: reading -------------------------------------------------------------------------------------------

def test_sample_incidents_cover_every_interesting_state(stub, who):
    everything = stub.incidents.search(who["admin1"], IncidentSearchCriteria())
    assert len(everything) == 8
    assert {i.status for i in everything} == {S.CLASSIFIED, S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.RESOLVED, S.VERIFIED, S.CLOSED}
    assert any(i.possible_duplicate_of for i in everything) and any(i.feedback for i in everything)
    assert any(i.sla_tracker.status is SlaStatus.VIOLATED for i in everything)


def test_search_is_scoped_by_role_and_filters_work(stub, who):
    s = stub.incidents
    assert {i.ticket_number for i in s.search(who["emp1"], IncidentSearchCriteria())} == {"INC-1001", "INC-1003", "INC-1006", "INC-1999"}
    assert {i.ticket_number for i in s.search(who["tech2"], IncidentSearchCriteria())} == {"INC-1003", "INC-1004"}
    assert [i.ticket_number for i in s.search(who["admin1"], IncidentSearchCriteria(status=S.CLOSED))] == ["INC-1006"]
    assert [i.ticket_number for i in s.search(who["admin1"], IncidentSearchCriteria(keyword="wifi"))] == ["INC-1007"]
    assert s.search(who["admin1"], IncidentSearchCriteria(from_date=date(2999, 1, 1))) == []


def test_viewing_rules_follow_the_real_ones(stub, who):
    s = stub.incidents
    assert s.get_incident(who["emp1"], 1).ticket_number == "INC-1001"
    with pytest.raises(UnauthorizedOperationError):
        s.get_incident(who["emp2"], 1)
    with pytest.raises(IncidentNotFoundError):
        s.get_incident(who["admin1"], 12345)
    trail = s.get_audit_trail(who["emp1"], 1)
    assert [r.action for r in trail][:3] == ["CREATED", "CLASSIFIED", "ASSIGNED"]


# ---- incidents: creating and the lifecycle -----------------------------------------------------------------------

def _request(**extra):
    base = dict(title="Payment page is down", description="Customers cannot pay", category_id=1, service_id=1,
                impact=Level.HIGH, urgency=Level.HIGH, affected_users=120)
    return CreateIncidentRequest(**{**base, **extra})


def test_creating_an_incident_prioritises_assigns_and_flags_duplicates(stub, who):
    incident = stub.incidents.create_incident(who["emp3"], _request(title="Payment transaction failing again"))
    assert incident.ticket_number == "INC-1010" and incident.priority is Priority.P1 and incident.priority_score == 27
    assert incident.status is S.ASSIGNED and incident.assigned_technician.username == "tech1"
    assert incident.possible_duplicate_of is not None                         # shares three words with an open Payment incident
    assert stub.notifications.unread_count(who["tech1"]) >= 2                 # the sample one plus this assignment
    for bad in (_request(title="  "), _request(affected_users=0)):
        with pytest.raises(InvalidInputError):
            stub.incidents.create_incident(who["emp3"], bad)


def test_the_whole_lifecycle_runs_through_the_domain_state_machine(stub, who):
    s, tech, emp = stub.incidents, who["tech1"], who["emp2"]                 # incident 2: ASSIGNED, tech1, reporter emp2
    assert s.acknowledge(tech, 2).status is S.ACKNOWLEDGED
    assert s.start_investigation(tech, 2).status is S.IN_PROGRESS
    s.add_note(tech, 2, "Reproduced it")
    s.request_info(tech, 2, "Which browser?")
    s.respond_to_info_request(emp, 2, "Firefox")
    assert s.resolve(tech, 2, "Fixed", "Restarted").status is S.RESOLVED
    assert s.reject_resolution(emp, 2, "Still broken").status is S.IN_PROGRESS
    s.resolve(tech, 2, "Fixed properly", "Patched")
    assert s.verify(emp, 2).status is S.VERIFIED
    assert s.close(emp, 2).status is S.CLOSED
    assert s.submit_feedback(emp, 2, 4, "Thanks").feedback.rating == 4
    actions = [r.action for r in s.get_audit_trail(emp, 2)]
    assert actions[-3:] == ["VERIFY", "CLOSE", "SUBMIT_FEEDBACK"]
    assert stub.notifications.unread_count(emp) >= 1


def test_illegal_transitions_and_wrong_actors_are_refused_exactly_as_in_real_mode(stub, who):
    s = stub.incidents
    with pytest.raises(InvalidStateTransitionError):
        s.close(who["emp2"], 2)                                               # ASSIGNED cannot be closed
    with pytest.raises(UnauthorizedOperationError):
        s.acknowledge(who["emp2"], 2)                                         # the reporter is not the technician
    with pytest.raises(UnauthorizedOperationError):
        s.acknowledge(who["tech2"], 2)                                        # a different technician cannot even see it


@pytest.mark.parametrize("call", [
    lambda s, w: s.acknowledge(w["tech1"], ERROR_INCIDENT_ID),
    lambda s, w: s.start_investigation(w["tech1"], ERROR_INCIDENT_ID),
    lambda s, w: s.add_note(w["tech1"], ERROR_INCIDENT_ID, "x"),
    lambda s, w: s.request_info(w["tech1"], ERROR_INCIDENT_ID, "x"),
    lambda s, w: s.respond_to_info_request(w["emp1"], ERROR_INCIDENT_ID, "x"),
    lambda s, w: s.resolve(w["tech1"], ERROR_INCIDENT_ID, "x", "y"),
    lambda s, w: s.verify(w["emp1"], ERROR_INCIDENT_ID),
    lambda s, w: s.reject_resolution(w["emp1"], ERROR_INCIDENT_ID, "x"),
    lambda s, w: s.close(w["emp1"], ERROR_INCIDENT_ID),
    lambda s, w: s.submit_feedback(w["emp1"], ERROR_INCIDENT_ID, 5, "x"),
    lambda s, w: s.assign(w["admin1"], ERROR_INCIDENT_ID, w["tech2"].id),
    lambda s, w: s.override_priority(w["admin1"], ERROR_INCIDENT_ID, Priority.P2, "x")])
def test_incident_999_refuses_every_action_with_an_invalid_transition_error(stub, who, call):
    with pytest.raises(InvalidStateTransitionError) as caught:
        call(stub.incidents, who)
    assert str(ERROR_INCIDENT_ID) in caught.value.message
    assert stub.incidents.get_incident(who["emp1"], ERROR_INCIDENT_ID).status is S.ASSIGNED    # unchanged


# ---- assignment and priority tools ---------------------------------------------------------------------------------

def test_assign_auto_assign_recommend_and_override(stub, who):
    s, admin = stub.incidents, who["admin1"]
    ranked = s.recommend_technicians(admin, 7)
    assert ranked and ranked[0].score >= ranked[-1].score and ranked[0].reasons
    assert s.assign(admin, 7, who["tech2"].id).assigned_technician.username == "tech2"
    assert s.assign(admin, 7, who["tech1"].id).assigned_technician.username == "tech1"        # reassign
    assert s.override_priority(admin, 7, Priority.P1, "Customer escalation").priority is Priority.P1
    with pytest.raises(InvalidInputError):
        s.assign(admin, 7, who["emp1"].id)
    with pytest.raises(UnauthorizedOperationError):
        s.assign(who["emp1"], 7, who["tech1"].id)
    for tech in ("tech1", "tech2"):                                                               # tech3 is already on leave
        stub.admin.set_technician_availability(admin, who[tech].id, False)
    stranded = s.create_incident(who["emp1"], _request(title="Network down", service_id=2, category_id=2))
    assert stranded.status is S.CLASSIFIED                                                        # nobody to take it
    with pytest.raises(TechnicianUnavailableError):
        s.auto_assign(admin, stranded.id)


# ---- lookup, admin, reports, notifications -------------------------------------------------------------------------

def test_lookup_lists(stub, who):
    assert [s.name for s in stub.lookup.list_active_services(who["emp1"])] == ["Payment", "Network", "Email", "Database"]
    assert len(stub.lookup.list_active_categories(who["emp1"])) == 3
    assert [t.username for t in stub.lookup.list_technicians(who["admin1"])] == ["tech1", "tech2", "tech3"]
    with pytest.raises(UnauthorizedOperationError):
        stub.lookup.list_technicians(who["emp1"])


def test_every_admin_method_works_and_refuses_non_administrators(stub, who):
    a, admin = stub.admin, who["admin1"]
    assert len(a.list_users(admin)) == 9
    tech = a.create_user(admin, CreateUserRequest("new.tech", "New Tech", "nt@x.com", PASSWORD, Role.TECHNICIAN, skills=("Network",)))
    assert tech.id and a.create_user(admin, CreateUserRequest("new.boss", "Boss", "b@x.com", PASSWORD, Role.ADMINISTRATOR,
                                                              admin_level=AdminLevel.IT_MANAGER)).admin_level is AdminLevel.IT_MANAGER
    for bad in (CreateUserRequest("emp1", "Dup", "d@x.com", PASSWORD, Role.EMPLOYEE),
                CreateUserRequest("shorty", "S", "s@x.com", "short", Role.EMPLOYEE)):
        with pytest.raises(InvalidInputError):
            a.create_user(admin, bad)
    assert a.deactivate_user(admin, who["emp3"].id).active is False and a.activate_user(admin, who["emp3"].id).active
    with pytest.raises(InvalidInputError):
        a.deactivate_user(admin, admin.id)
    assert a.set_technician_availability(admin, who["tech3"].id, True).available is True

    service = a.create_service(admin, ServiceRequest("ERP", "Finance system", Level.MEDIUM))
    assert a.update_service(admin, service.id, ServiceRequest("ERP", "Changed", Level.LOW, None, False)).active is False
    category = a.create_category(admin, CategoryRequest("Storage", "Disks", "Storage"))
    assert a.update_category(admin, category.id, CategoryRequest("Storage", "Changed", "Storage", False)).active is False
    assert len(a.list_services(admin)) == 5 and len(a.list_categories(admin)) == 4

    policy = a.save_sla_policy(admin, SlaPolicyRequest("Strict", True, TARGETS))
    assert [p.is_default for p in a.list_sla_policies(admin)].count(True) == 1 and policy.is_default
    with pytest.raises(InvalidInputError):
        a.save_sla_policy(admin, SlaPolicyRequest("Partial", False, {Priority.P1: (1, 2)}))

    assert a.list_assignment_strategies(admin) == ["skill_based", "load_based", "weighted_recommendation"]
    a.set_assignment_strategy(admin, "load_based")
    a.set_priority_strategy(admin, "rule_based")
    assert (a.get_assignment_strategy(admin), a.get_priority_strategy(admin)) == ("load_based", "rule_based")
    assert a.list_priority_strategies(admin) == ["weighted_score", "rule_based"]
    with pytest.raises(InvalidInputError):
        a.set_assignment_strategy(admin, "nonsense")

    assert a.is_time_simulated(admin) is True
    before = a.get_current_time(admin)
    assert a.advance_time(admin, 30) - before >= timedelta(minutes=29)
    assert a.reset_time(admin) - before < timedelta(minutes=1)
    with pytest.raises(InvalidInputError):
        a.advance_time(admin, 0)
    assert isinstance(a.run_sla_check_now(admin), int) and isinstance(a.run_escalation_check_now(admin), int)

    for call in (a.list_users, a.list_services, a.list_categories, a.list_sla_policies, a.get_current_time, a.reset_time,
                 a.run_sla_check_now, a.run_escalation_check_now):
        for outsider in (who["emp1"], who["tech1"]):
            with pytest.raises(UnauthorizedOperationError):
                call(outsider)


def test_advancing_the_clock_changes_what_the_stub_checks_report(stub, who):
    admin = who["admin1"]
    assert stub.admin.run_escalation_check_now(admin) == 0
    stub.admin.advance_time(admin, 20)                                      # the P1 assigned 3 minutes ago is now late
    assert stub.admin.run_escalation_check_now(admin) >= 1


def test_reports(stub, who):
    r, admin = stub.reports, who["admin1"]
    overview = r.overview(admin)
    assert (overview.total, overview.open, overview.resolved) == (8, 5, 3) and overview.critical_open >= 1
    assert overview.sla_violations >= 1
    assert {row.technician_name for row in r.technician_workload(admin)} == {"Ravi Kumar", "Priya Menon", "Arjun Das"}
    assert sum(row.count for row in r.service_analysis(admin)) == 8 == sum(row.count for row in r.category_analysis(admin))
    assert r.sla_violations(admin) and r.audit_log(admin, AuditFilter(incident_id=1))
    assert r.audit_log(admin, AuditFilter(action="CLOSED")) and r.correlation_groups(admin) == []
    for call in (r.overview, r.technician_workload, r.service_analysis, r.category_analysis, r.sla_violations):
        with pytest.raises(UnauthorizedOperationError):
            call(who["emp1"])


def test_notifications(stub, who):
    n, emp = stub.notifications, who["emp1"]
    assert n.unread_count(emp) == 2 and len(n.list_for_user(emp, 10)) == 2
    first = n.list_for_user(emp, 10)[0]
    n.mark_read(emp, first.id)
    assert n.unread_count(emp) == 1
    n.mark_all_read(emp)
    assert n.unread_count(emp) == 0
    with pytest.raises(UnauthorizedOperationError):
        n.mark_read(who["tech1"], first.id)                                  # not theirs


# ---- the whole app in stub mode ---------------------------------------------------------------------------------------

@pytest.fixture
def stub_app(tmp_path):
    return create_app(Settings(ITSM_MODE="stub", ENABLE_SCHEDULER=False, SEED_DEMO_DATA=False,
                               DATABASE_PATH=str(tmp_path / "unused.db"), EMAIL_LOG_PATH=str(tmp_path / "e.log")))


@pytest.mark.parametrize("who_,url,expected", [("emp1", "/employee/dashboard", "Payment application unavailable"),
                                               ("tech1", "/tech/dashboard", "Payment transaction failing"),
                                               ("admin1", "/admin/dashboard", "Total incidents")])
def test_the_app_runs_in_stub_mode_with_sample_data(stub_app, who_, url, expected):
    client = TestClient(stub_app, follow_redirects=False)
    assert client.post("/login", data={"username": who_, "password": PASSWORD}).status_code == 303
    response = client.get(url)
    assert response.status_code == 200 and expected in response.text
    assert client.get("/notifications").status_code == 200
