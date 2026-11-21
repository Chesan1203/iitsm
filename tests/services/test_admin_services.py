"""P3 T4: admin, lookup, report and notification services, and the strategy registry."""
from datetime import datetime, timedelta

import pytest

from app.domain.enums import (
    AdminLevel,
    ChannelType,
    IncidentEventType,
    Level,
    Priority,
    Role,
    SlaEventType,
)
from app.domain.exceptions import (
    CategoryNotFoundError,
    InvalidInputError,
    ServiceNotFoundError,
    UnauthorizedOperationError,
    UserNotFoundError,
)
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent
from app.domain.models.user import Technician, User
from app.domain.time_provider import SimulatedTimeProvider
from app.ports.dto import (
    AuditFilter,
    CategoryRequest,
    CreateUserRequest,
    ServiceRequest,
    SlaPolicyRequest,
)
from app.services.impl.admin_service import AdminServiceImpl
from app.services.impl.lookup_service import LookupServiceImpl
from app.services.impl.notification_service import NotificationServiceImpl
from app.services.impl.report_service import ReportServiceImpl
from app.services.security.access_policy import AccessPolicy

from .helpers import ManualTime, assign, at, classify, new_incident

ALL_TARGETS = {Priority.P1: (5, 30), Priority.P2: (15, 120), Priority.P3: (60, 480), Priority.P4: (240, 1440)}


@pytest.fixture
def clock():
    return SimulatedTimeProvider()


@pytest.fixture
def counters():
    return {"sla": 0, "escalation": 0}


@pytest.fixture
def admin_service(repos, world, factory, priority_registry, assignment_registry, clock, counters):
    def run_sla():
        counters["sla"] += 1
        return 7

    def run_escalation():
        counters["escalation"] += 1
        return 2
    return AdminServiceImpl(repos.users, repos.services, repos.categories, repos.policies, factory,
                            priority_registry, assignment_registry, clock, AccessPolicy(),
                            run_sla, run_escalation)


def _user_request(**extra):
    base = dict(username="new.tech", full_name="New Tech", email="nt@x.com", password="Password@123",
                role=Role.TECHNICIAN, skills=("Network",), experience_years=2)
    return CreateUserRequest(**{**base, **extra})


# ---- authorization: every admin method refuses non-administrators ------------------------------------------

ADMIN_CALLS = [
    ("list_users", lambda s, a, w: s.list_users(a)),
    ("create_user", lambda s, a, w: s.create_user(a, _user_request())),
    ("deactivate_user", lambda s, a, w: s.deactivate_user(a, w.tech.id)),
    ("activate_user", lambda s, a, w: s.activate_user(a, w.tech.id)),
    ("set_technician_availability", lambda s, a, w: s.set_technician_availability(a, w.tech.id, False)),
    ("list_services", lambda s, a, w: s.list_services(a)),
    ("create_service", lambda s, a, w: s.create_service(a, ServiceRequest("X", "", Level.LOW))),
    ("update_service", lambda s, a, w: s.update_service(a, w.service.id, ServiceRequest("X", "", Level.LOW))),
    ("list_categories", lambda s, a, w: s.list_categories(a)),
    ("create_category", lambda s, a, w: s.create_category(a, CategoryRequest("X", "", "x"))),
    ("update_category", lambda s, a, w: s.update_category(a, w.category.id, CategoryRequest("X", "", "x"))),
    ("list_sla_policies", lambda s, a, w: s.list_sla_policies(a)),
    ("save_sla_policy", lambda s, a, w: s.save_sla_policy(a, SlaPolicyRequest("X", False, ALL_TARGETS))),
    ("list_assignment_strategies", lambda s, a, w: s.list_assignment_strategies(a)),
    ("get_assignment_strategy", lambda s, a, w: s.get_assignment_strategy(a)),
    ("set_assignment_strategy", lambda s, a, w: s.set_assignment_strategy(a, "load_based")),
    ("list_priority_strategies", lambda s, a, w: s.list_priority_strategies(a)),
    ("get_priority_strategy", lambda s, a, w: s.get_priority_strategy(a)),
    ("set_priority_strategy", lambda s, a, w: s.set_priority_strategy(a, "rule_based")),
    ("is_time_simulated", lambda s, a, w: s.is_time_simulated(a)),
    ("get_current_time", lambda s, a, w: s.get_current_time(a)),
    ("advance_time", lambda s, a, w: s.advance_time(a, 5)),
    ("reset_time", lambda s, a, w: s.reset_time(a)),
    ("run_sla_check_now", lambda s, a, w: s.run_sla_check_now(a)),
    ("run_escalation_check_now", lambda s, a, w: s.run_escalation_check_now(a)),
]


@pytest.mark.parametrize("name,call", ADMIN_CALLS, ids=[n for n, _ in ADMIN_CALLS])
@pytest.mark.parametrize("who", ["reporter", "tech", "system", "nobody"])
def test_non_administrators_are_refused_by_every_admin_method(admin_service, world, name, call, who):
    actor = {"reporter": world.reporter, "tech": world.tech, "system": User.system(), "nobody": None}[who]
    with pytest.raises(UnauthorizedOperationError):
        call(admin_service, actor, world)


@pytest.mark.parametrize("name,call", [c for c in ADMIN_CALLS if c[0].startswith(("list_", "get_", "is_"))],
                         ids=lambda v: v if isinstance(v, str) else "")
def test_administrators_may_use_the_read_methods(admin_service, world, name, call):
    assert call(admin_service, world.admin, world) is not None


# ---- users --------------------------------------------------------------------------------------------------------

def test_create_user_for_each_role_and_login_ready_password(admin_service, world, hasher):
    tech = admin_service.create_user(world.admin, _user_request())
    assert isinstance(tech, Technician) and tech.id is not None and hasher.verify("Password@123", tech.password_hash)
    admin = admin_service.create_user(world.admin, _user_request(username="boss", role=Role.ADMINISTRATOR,
                                                                  admin_level=AdminLevel.IT_MANAGER))
    assert admin.admin_level is AdminLevel.IT_MANAGER
    assert len(admin_service.list_users(world.admin)) == len(world.repos.users.find_all())


def test_create_user_rejects_duplicates_and_bad_input(admin_service, world):
    with pytest.raises(InvalidInputError) as taken:
        admin_service.create_user(world.admin, _user_request(username="tech1"))
    assert taken.value.field == "username"
    with pytest.raises(InvalidInputError):
        admin_service.create_user(world.admin, _user_request(password="short"))
    with pytest.raises(InvalidInputError):
        admin_service.create_user(world.admin, _user_request(role=Role.ADMINISTRATOR))     # no admin level


def test_deactivate_and_activate_keep_the_user_and_their_history(admin_service, world):
    off = admin_service.deactivate_user(world.admin, world.reporter.id)
    assert off.active is False and world.repos.users.find_by_id(world.reporter.id).active is False
    assert admin_service.activate_user(world.admin, world.reporter.id).active is True
    assert len(world.repos.users.find_all()) == 7                  # never deleted


def test_an_administrator_cannot_deactivate_themselves_and_unknown_users_are_reported(admin_service, world):
    with pytest.raises(InvalidInputError):
        admin_service.deactivate_user(world.admin, world.admin.id)
    for call in (admin_service.deactivate_user, admin_service.activate_user):
        with pytest.raises(UserNotFoundError):
            call(world.admin, 999)


def test_technician_availability_can_be_changed_for_technicians_only(admin_service, world):
    assert admin_service.set_technician_availability(world.admin, world.tech.id, False).available is False
    assert world.repos.users.find_by_id(world.tech.id).available is False
    with pytest.raises(InvalidInputError):
        admin_service.set_technician_availability(world.admin, world.reporter.id, False)
    with pytest.raises(UserNotFoundError):
        admin_service.set_technician_availability(world.admin, 999, True)


# ---- services and categories -----------------------------------------------------------------------------------------

def test_create_and_update_a_service(admin_service, world):
    created = admin_service.create_service(world.admin, ServiceRequest("  Cloud   Storage ", "Files", Level.MEDIUM, world.policy.id))
    assert created.id and created.name == "Cloud Storage" and created.sla_policy_id == world.policy.id
    updated = admin_service.update_service(world.admin, created.id, ServiceRequest("Cloud Storage", "New text", Level.HIGH, None, False))
    assert (updated.id, updated.description, updated.active, updated.business_criticality) == (created.id, "New text", False, Level.HIGH)
    assert len(admin_service.list_services(world.admin)) == 2


def test_duplicate_service_name_is_rejected_ignoring_case_and_unknown_things_are_reported(admin_service, world):
    with pytest.raises(InvalidInputError) as caught:
        admin_service.create_service(world.admin, ServiceRequest("payment", "", Level.LOW))
    assert caught.value.field == "name"
    other = admin_service.create_service(world.admin, ServiceRequest("Email", "", Level.LOW))
    with pytest.raises(InvalidInputError):
        admin_service.update_service(world.admin, other.id, ServiceRequest("PAYMENT", "", Level.LOW))
    admin_service.update_service(world.admin, other.id, ServiceRequest("Email", "same name is fine", Level.LOW))
    with pytest.raises(InvalidInputError):
        admin_service.create_service(world.admin, ServiceRequest("VPN", "", Level.LOW, sla_policy_id=999))
    with pytest.raises(ServiceNotFoundError):
        admin_service.update_service(world.admin, 999, ServiceRequest("X", "", Level.LOW))
    with pytest.raises(InvalidInputError):
        admin_service.create_service(world.admin, ServiceRequest("   ", "", Level.LOW))


def test_categories_create_update_and_uniqueness(admin_service, world):
    created = admin_service.create_category(world.admin, CategoryRequest("Network", "Net", "Network"))
    updated = admin_service.update_category(world.admin, created.id, CategoryRequest("Network", "Changed", "Net", False))
    assert (updated.description, updated.required_skill, updated.active) == ("Changed", "Net", False)
    with pytest.raises(InvalidInputError):
        admin_service.create_category(world.admin, CategoryRequest("database", "", "Database"))
    with pytest.raises(CategoryNotFoundError):
        admin_service.update_category(world.admin, 999, CategoryRequest("X", "", "x"))


# ---- SLA policies ------------------------------------------------------------------------------------------------------------

def test_policy_missing_a_priority_is_rejected(admin_service, world):
    incomplete = {p: t for p, t in ALL_TARGETS.items() if p is not Priority.P3}
    with pytest.raises(InvalidInputError) as caught:
        admin_service.save_sla_policy(world.admin, SlaPolicyRequest("Partial", False, incomplete))
    assert "P3" in caught.value.message and caught.value.field == "targets"


@pytest.mark.parametrize("bad", [(0, 30), (-5, 30), (40, 30), ("5", 30), (5.5, 30), (5,), None])
def test_policy_targets_must_be_sensible_whole_minutes(admin_service, world, bad):
    with pytest.raises(InvalidInputError):
        admin_service.save_sla_policy(world.admin, SlaPolicyRequest("Bad", False, {**ALL_TARGETS, Priority.P2: bad}))


def test_a_new_default_policy_demotes_the_old_one_so_exactly_one_default_remains(admin_service, world, repos):
    strict = admin_service.save_sla_policy(world.admin, SlaPolicyRequest("Strict", True, {p: (1, 2) for p in Priority}))
    defaults = [p for p in repos.policies.find_all() if p.is_default]
    assert [p.name for p in defaults] == ["Strict"] and defaults[0].id == strict.id
    assert repos.policies.find_by_id(world.policy.id).targets == world.policy.targets      # old one kept its targets


def test_saving_a_policy_with_an_existing_name_updates_it(admin_service, world, repos):
    admin_service.save_sla_policy(world.admin, SlaPolicyRequest("default", True, {p: (10, 20) for p in Priority}))
    policies = repos.policies.find_all()
    assert len(policies) == 1 and policies[0].id == world.policy.id
    assert policies[0].target_for(Priority.P1).response_minutes == 10


def test_the_only_default_policy_cannot_be_unset(admin_service, world):
    with pytest.raises(InvalidInputError) as caught:
        admin_service.save_sla_policy(world.admin, SlaPolicyRequest("Default", False, ALL_TARGETS))
    assert caught.value.field == "is_default"
    extra = admin_service.save_sla_policy(world.admin, SlaPolicyRequest("Extra", False, ALL_TARGETS))
    assert extra.is_default is False


# ---- strategies --------------------------------------------------------------------------------------------------------------

def test_strategy_lists_defaults_and_validation(admin_service, world):
    a = world.admin
    assert admin_service.list_assignment_strategies(a) == ["skill_based", "load_based", "weighted_recommendation"]
    assert admin_service.list_priority_strategies(a) == ["weighted_score", "rule_based"]
    assert admin_service.get_assignment_strategy(a) == "skill_based" and admin_service.get_priority_strategy(a) == "weighted_score"
    for setter in (admin_service.set_assignment_strategy, admin_service.set_priority_strategy):
        with pytest.raises(InvalidInputError):
            setter(a, "does_not_exist")
    assert admin_service.get_assignment_strategy(a) == "skill_based"


def test_switching_strategy_takes_effect_immediately_without_a_restart(admin_service, world, assignment_registry, priority_registry):
    admin_service.set_assignment_strategy(world.admin, "load_based")
    admin_service.set_priority_strategy(world.admin, "rule_based")
    assert assignment_registry.active().name == "load_based" and priority_registry.active().name == "rule_based"
    assert world.repos.settings.get("assignment.strategy") == "load_based"


def test_an_unknown_stored_strategy_name_falls_back_to_the_default(world, assignment_registry):
    world.repos.settings.put("assignment.strategy", "deleted_strategy")
    assert assignment_registry.active_name() == "skill_based"


# ---- demo clock and manual runs -------------------------------------------------------------------------------------------------

def test_demo_clock_can_be_advanced_and_reset_when_time_is_simulated(admin_service, world, clock):
    assert admin_service.is_time_simulated(world.admin) is True
    new_time = admin_service.advance_time(world.admin, 30)
    assert clock.offset == timedelta(minutes=30)
    assert abs((new_time - datetime.now()) - timedelta(minutes=30)) < timedelta(seconds=5)
    admin_service.advance_time(world.admin, 15)
    assert clock.offset == timedelta(minutes=45)
    admin_service.reset_time(world.admin)
    assert clock.offset == timedelta(0)
    assert abs(admin_service.get_current_time(world.admin) - datetime.now()) < timedelta(seconds=5)


@pytest.mark.parametrize("bad", [0, -5, 2.5, "10", True, None])
def test_advancing_time_needs_a_positive_whole_number_of_minutes(admin_service, world, bad):
    with pytest.raises(InvalidInputError):
        admin_service.advance_time(world.admin, bad)


def test_demo_clock_controls_are_refused_with_the_real_clock(repos, world, factory, priority_registry, assignment_registry):
    service = AdminServiceImpl(repos.users, repos.services, repos.categories, repos.policies, factory,
                               priority_registry, assignment_registry, ManualTime(), AccessPolicy(),
                               lambda: 0, lambda: 0)
    assert service.is_time_simulated(world.admin) is False
    for call in (lambda: service.advance_time(world.admin, 5), lambda: service.reset_time(world.admin)):
        with pytest.raises(InvalidInputError):
            call()


def test_manual_sla_and_escalation_runs_report_what_the_jobs_return(admin_service, world, counters):
    assert admin_service.run_sla_check_now(world.admin) == 7
    assert admin_service.run_escalation_check_now(world.admin) == 2
    assert counters == {"sla": 1, "escalation": 1}


# ---- lookup -----------------------------------------------------------------------------------------------------------------------

def test_lookup_lists_only_active_things_and_technicians_only_for_administrators(repos, world):
    lookup = LookupServiceImpl(repos.services, repos.categories, repos.users, AccessPolicy())
    from app.domain.models.category import Category
    from app.domain.models.it_service import ITService
    repos.services.save(ITService("Retired", "", Level.LOW, active=False))
    repos.categories.save(Category("Old", "", "x", active=False))
    assert [s.name for s in lookup.list_active_services(world.reporter)] == ["Payment"]
    assert [c.name for c in lookup.list_active_categories(world.tech)] == ["Database"]
    assert [t.username for t in lookup.list_technicians(world.admin)] == ["tech1", "tech2"]
    with pytest.raises(UnauthorizedOperationError):
        lookup.list_technicians(world.reporter)
    with pytest.raises(UnauthorizedOperationError):
        lookup.list_active_services(None)


def test_lookup_hides_deactivated_technicians(repos, world):
    lookup = LookupServiceImpl(repos.services, repos.categories, repos.users, AccessPolicy())
    gone = repos.users.find_by_id(world.tech.id)
    gone.deactivate()
    repos.users.save(gone)
    assert [t.username for t in lookup.list_technicians(world.admin)] == ["tech2"]


# ---- reports ------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def reports(repos):
    return ReportServiceImpl(repos.reports, repos.audits, repos.incidents, CorrelationDetector(),
                             ManualTime(at(30)), AccessPolicy())


def test_reports_are_for_administrators_only(reports, world):
    for call in (reports.overview, reports.technician_workload, reports.service_analysis,
                 reports.category_analysis, reports.sla_violations, reports.correlation_groups,
                 lambda a: reports.audit_log(a, AuditFilter())):
        for actor in (world.reporter, world.tech, None):
            with pytest.raises(UnauthorizedOperationError):
                call(actor)


def test_reports_pass_through_the_repository_numbers(reports, world, repos):
    first = assign(classify(new_incident(world)), world.tech)
    repos.incidents.save(first)
    repos.sla_events.save(SlaEvent(incident_id=first.id, event_type=SlaEventType.RESPONSE_VIOLATED, recorded_at=at(9)))
    new_incident(world, "Second")
    overview = reports.overview(world.admin)
    assert (overview.total, overview.open, overview.critical_open, overview.sla_violations) == (2, 2, 1, 1)
    assert {r.technician_name: r.active_count for r in reports.technician_workload(world.admin)} == {"Ravi K": 1, "Priya M": 0}
    assert reports.service_analysis(world.admin)[0].count == 2 and reports.category_analysis(world.admin)[0].label == "Database"
    assert reports.sla_violations(world.admin)[0].ticket_number == "INC-1001"


def test_audit_log_applies_the_filter(reports, world, repos):
    from app.domain.models.audit import AuditRecord
    for action in ("CREATED", "ASSIGNED"):
        repos.audits.save(AuditRecord(incident_id=1, ticket_number="INC-1001", timestamp=at(1),
                                      actor_id=0, actor_name="System", action=action))
    assert [r.action for r in reports.audit_log(world.admin, AuditFilter(action="ASSIGNED"))] == ["ASSIGNED"]


def test_correlation_groups_flag_three_open_incidents_on_one_service(reports, world):
    for n in range(3):
        new_incident(world, f"Payment issue {n}", created_at=at(10 + n))
    groups = reports.correlation_groups(world.admin)
    assert len(groups) == 1 and groups[0].is_probable_service_problem and len(groups[0].incidents) == 3


# ---- notifications -----------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def notifier(repos):
    return NotificationServiceImpl(repos.notifications, AccessPolicy())


def _note(repos, recipient, minutes=0, message="Hi"):
    return repos.notifications.save(Notification(
        recipient_id=recipient.id, incident_id=1, event_type=IncidentEventType.CREATED,
        channel=ChannelType.IN_APP, message=message, created_at=at(minutes)))


def test_a_user_lists_counts_and_marks_only_their_own_notifications(notifier, world, repos):
    mine = [_note(repos, world.reporter, m, f"m{m}") for m in range(3)]
    theirs = _note(repos, world.tech)
    assert [n.message for n in notifier.list_for_user(world.reporter, 2)] == ["m2", "m1"]
    assert notifier.unread_count(world.reporter) == 3
    notifier.mark_read(world.reporter, mine[0].id)
    assert notifier.unread_count(world.reporter) == 2
    with pytest.raises(UnauthorizedOperationError):
        notifier.mark_read(world.reporter, theirs.id)                      # someone else's
    with pytest.raises(UnauthorizedOperationError):
        notifier.mark_read(world.reporter, 999)                            # does not exist: same answer
    assert notifier.unread_count(world.tech) == 1                          # untouched


def test_mark_all_read_only_touches_the_actors_notifications(notifier, world, repos):
    _note(repos, world.reporter)
    _note(repos, world.reporter)
    _note(repos, world.tech)
    notifier.mark_all_read(world.reporter)
    assert notifier.unread_count(world.reporter) == 0 and notifier.unread_count(world.tech) == 1


def test_notification_service_needs_a_signed_in_user_and_clamps_the_limit(notifier, world, repos):
    for call in (lambda: notifier.list_for_user(None, 5), lambda: notifier.unread_count(User.system()),
                 lambda: notifier.mark_all_read(None)):
        with pytest.raises(UnauthorizedOperationError):
            call()
    _note(repos, world.reporter)
    assert len(notifier.list_for_user(world.reporter, 0)) == 1             # a limit below 1 still returns one
    assert len(notifier.list_for_user(world.reporter, 10_000)) == 1
