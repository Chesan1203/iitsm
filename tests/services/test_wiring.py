"""P3 T7: the composition root. Fast tests assemble the services over the fakes; the rest use
the real SQLite database seeded once, and play the three demo workflows through the Container
alone, exactly as the web layer will."""
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.domain.enums import (
    EscalationLevel, IncidentStatus as S, Level, Priority, Role, SlaStatus,
)
from app.domain.exceptions import InvalidLoginError
from app.domain.time_provider import SimulatedTimeProvider, SystemTimeProvider
from app.ports.container import Container
from app.ports.dto import AuditFilter, IncidentSearchCriteria, RegisterRequest
from app.ports.services import (
    AdminService, AuthService, IncidentService, LookupService, NotificationService, ReportService,
)
from app.services.security.password_hasher import PasswordHasher
from app.services.wiring import RealContainer, assemble_container, build_real_container

from .fakes import FakeRepositories
from .helpers import T0, ManualTime, make_world, request

PASSWORD = "Password@123"


# ====================================================================================================
# Assembled over the in-memory fakes (fast)
# ====================================================================================================

def test_assembly_provides_all_six_services_of_the_right_type(tmp_path):
    container = assemble_container(FakeRepositories(), time_provider=ManualTime(T0),
                                   email_log_path=tmp_path / "e.log", hasher=PasswordHasher(rounds=4))
    assert isinstance(container, Container) and isinstance(container, RealContainer)
    for attribute, interface in (("auth", AuthService), ("incidents", IncidentService),
                                 ("lookup", LookupService), ("admin", AdminService),
                                 ("reports", ReportService), ("notifications", NotificationService)):
        assert isinstance(getattr(container, attribute), interface), attribute
    assert container.scheduler.running is False                  # assembling never starts a thread
    container.close()                                            # and closing an unstarted container is fine


def test_a_new_employee_can_register_log_in_report_and_be_notified_through_the_container(tmp_path):
    repos = FakeRepositories()
    w = make_world(repos)
    clock = ManualTime(T0)
    c = assemble_container(repos, time_provider=clock, email_log_path=tmp_path / "e.log",
                           hasher=PasswordHasher(rounds=4))
    c.auth.register_employee(RegisterRequest("newbie", "New Bie", "nb@x.com", PASSWORD, "Ops"))
    me = c.auth.login("newbie", PASSWORD)
    service = c.lookup.list_active_services(me)[0]
    category = c.lookup.list_active_categories(me)[0]
    incident = c.incidents.create_incident(me, request(w, "Payment is slow", service_id=service.id,
                                                       category_id=category.id))
    assert incident.status is S.ASSIGNED and incident.reporter.username == "newbie"
    assert c.notifications.unread_count(me) >= 1
    assert [i.id for i in c.incidents.search(me, IncidentSearchCriteria())] == [incident.id]
    assert c.reports.overview(w.admin).total == 1
    assert c.admin.run_sla_check_now(w.admin) == 0 and c.admin.run_escalation_check_now(w.admin) == 0
    assert (tmp_path / "e.log").read_text(encoding="utf-8").count("Simulated email") >= 1
    assert c.admin.get_assignment_strategy(w.admin) == "skill_based"


def test_the_manual_job_buttons_use_the_same_jobs_as_the_scheduler(tmp_path):
    repos = FakeRepositories()
    w = make_world(repos)
    clock = ManualTime(T0)
    c = assemble_container(repos, time_provider=clock, email_log_path=tmp_path / "e.log",
                           hasher=PasswordHasher(rounds=4))
    c.incidents.create_incident(w.reporter, request(w))
    clock.advance(6)                                             # past the 5-minute response deadline
    assert c.admin.run_sla_check_now(w.admin) == 1
    assert c.admin.run_sla_check_now(w.admin) == 0               # once only
    assert c.admin.run_escalation_check_now(w.admin) == 1        # P1 still unacknowledged
    assert c.sla_job.run_once() == 0 and c.escalation_job.run_once() == 0


# ====================================================================================================
# The real SQLite database
# ====================================================================================================

def real_settings(directory: Path, db_name="iitsm.db", **overrides) -> Settings:
    values = dict(DATABASE_PATH=str(directory / db_name), EMAIL_LOG_PATH=str(directory / "emails.log"),
                  ENABLE_SCHEDULER=False, SEED_DEMO_DATA=True, SIMULATED_TIME=True)
    return Settings(**{**values, **overrides})


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """Seeded once (about ten seconds). Each test then works on its own copy of the file."""
    directory = tmp_path_factory.mktemp("template")
    container = build_real_container(real_settings(directory))
    admin = container.auth.login("admin1", PASSWORD)
    actors = {name: container.auth.login(name, PASSWORD)
              for name in ("admin1", "admin3", "tech1", "tech2", "tech3", "tech4", "tech5", "emp1", "emp2")}
    container.close()
    return SimpleNamespace(db_file=directory / "iitsm.db", actors=actors, admin=admin)


@pytest.fixture
def real(template, tmp_path):
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(template.db_file) + suffix)
        if source.exists():
            shutil.copy(source, tmp_path / ("copy.db" + suffix))
    container = build_real_container(real_settings(tmp_path, "copy.db"))
    yield container, template.actors, tmp_path
    container.close()


def test_the_first_start_creates_and_seeds_the_database(template):
    assert template.db_file.exists()
    assert len(template.actors) == 9


def test_starting_again_on_the_seeded_database_changes_nothing(real):
    container, actors, _ = real
    assert container.reports.overview(actors["admin1"]).total == 45


def test_demo_logins_work_and_a_wrong_password_does_not(real):
    container, actors, _ = real
    for name, role in (("admin1", Role.ADMINISTRATOR), ("tech1", Role.TECHNICIAN), ("emp1", Role.EMPLOYEE)):
        assert container.auth.login(name, PASSWORD).role is role
    with pytest.raises(InvalidLoginError):
        container.auth.login("admin1", "wrong")


def test_seeding_can_be_switched_off_and_the_database_is_still_created(tmp_path):
    container = build_real_container(real_settings(tmp_path, SEED_DEMO_DATA=False))
    assert (tmp_path / "iitsm.db").exists()
    with pytest.raises(InvalidLoginError):
        container.auth.login("admin1", PASSWORD)                 # nobody exists
    container.close()


def test_the_scheduler_starts_only_when_enabled_and_close_stops_it(tmp_path):
    off = build_real_container(real_settings(tmp_path, "off.db", SEED_DEMO_DATA=False))
    assert off.scheduler.running is False
    on = build_real_container(real_settings(tmp_path, "on.db", SEED_DEMO_DATA=False, ENABLE_SCHEDULER=True))
    try:
        assert on.scheduler.running is True
    finally:
        on.close()
    assert on.scheduler.running is False


def test_the_clock_is_simulated_or_real_according_to_the_settings(tmp_path):
    simulated = build_real_container(real_settings(tmp_path, "s.db", SEED_DEMO_DATA=False))
    real_clock = build_real_container(real_settings(tmp_path, "r.db", SEED_DEMO_DATA=False, SIMULATED_TIME=False))
    assert isinstance(simulated.time_provider, SimulatedTimeProvider)
    assert isinstance(real_clock.time_provider, SystemTimeProvider)


# ---- the three demo workflows, on the real database, through the container only ---------------------------

def test_workflow_1_an_employee_reports_the_system_prioritises_assigns_and_notifies(real):
    container, actors, directory = real
    emp, admin = actors["emp1"], actors["admin1"]
    payment = next(s for s in container.lookup.list_active_services(emp) if s.name == "Payment")
    application = next(c for c in container.lookup.list_active_categories(emp) if c.name == "Application")
    unread_before = container.notifications.unread_count(emp)

    incident = container.incidents.create_incident(emp, request_for(payment, application, "Payment page is down"))

    assert incident.ticket_number == "INC-1046" and incident.priority is Priority.P1
    assert incident.status is S.ASSIGNED and incident.assigned_technician is not None
    assert incident.possible_duplicate_of is not None             # matches the planted payment incidents
    assert incident.sla_tracker.response_deadline == incident.created_at + timedelta(minutes=3)   # Payment's strict policy
    assert container.notifications.unread_count(emp) > unread_before
    trail = [r.action for r in container.incidents.get_audit_trail(emp, incident.id)]
    assert trail == ["CREATED", "DUPLICATE_FLAGGED", "CLASSIFIED", "ASSIGNED"]
    assert "INC-1046" in (directory / "emails.log").read_text(encoding="utf-8")
    assert container.reports.overview(admin).total == 46


def test_workflow_2_a_technician_investigates_the_sla_is_monitored_and_the_user_is_notified(real):
    container, actors, _ = real
    emp, admin = actors["emp1"], actors["admin1"]
    payment = next(s for s in container.lookup.list_active_services(emp) if s.name == "Payment")
    application = next(c for c in container.lookup.list_active_categories(emp) if c.name == "Application")
    incident = container.incidents.create_incident(emp, request_for(payment, application, "Receipts missing again"))
    tech = actors[incident.assigned_technician.username]

    container.incidents.acknowledge(tech, incident.id)
    container.incidents.start_investigation(tech, incident.id)
    container.incidents.add_note(tech, incident.id, "Reproduced on the test environment")
    container.admin.advance_time(admin, 25)                       # past Payment's 20-minute P1 resolution window
    assert container.admin.run_sla_check_now(admin) >= 1
    assert container.incidents.get_incident(admin, incident.id).sla_tracker.status is SlaStatus.VIOLATED
    container.incidents.resolve(tech, incident.id, "Restarted the receipt worker", "The worker had stalled")
    assert any("resolved" in n.message for n in container.notifications.list_for_user(emp, 20))
    container.incidents.verify(emp, incident.id)
    container.incidents.close(emp, incident.id)
    done = container.incidents.submit_feedback(emp, incident.id, 5, "Quick")
    assert done.status is S.CLOSED and done.feedback.rating == 5
    violations = container.reports.sla_violations(admin)
    assert any(v.ticket_number == incident.ticket_number for v in violations)
    assert container.reports.audit_log(admin, AuditFilter(incident_id=incident.id))


def test_workflow_3_related_incidents_are_correlated_and_an_unacknowledged_p1_escalates(real):
    container, actors, _ = real
    admin, manager = actors["admin1"], actors["admin3"]

    groups = container.reports.correlation_groups(admin)
    probable = [g for g in groups if g.is_probable_service_problem]
    assert [(g.service.name, len(g.incidents)) for g in probable] == [("Network", 3)]

    def planted():
        found = container.incidents.search(admin, IncidentSearchCriteria(keyword="Primary database cluster"))
        assert len(found) == 1
        return found[0]
    assert planted().status is S.ASSIGNED and planted().priority is Priority.P1
    assert container.admin.run_escalation_check_now(admin) == 0   # response deadline not passed yet

    for minutes, level in ((4, EscalationLevel.TEAM_LEAD), (10, EscalationLevel.SYSTEM_ADMIN),
                           (10, EscalationLevel.IT_MANAGER)):
        container.admin.advance_time(admin, minutes)
        assert container.admin.run_escalation_check_now(admin) == 1
        assert planted().escalation_level is level
        assert container.admin.run_escalation_check_now(admin) == 0   # polling again changes nothing
    assert any("escalated" in n.message for n in container.notifications.list_for_user(manager, 50))
    assert [r.action for r in container.incidents.get_audit_trail(admin, planted().id)].count("ESCALATED") == 3
    container.admin.reset_time(admin)
    assert abs(container.admin.get_current_time(admin) - datetime.now()) < timedelta(seconds=5)


def test_switching_the_assignment_strategy_through_the_container_changes_the_next_assignment(real):
    container, actors, _ = real
    admin, emp = actors["admin1"], actors["emp2"]
    network = next(s for s in container.lookup.list_active_services(emp) if s.name == "Network")
    category = next(c for c in container.lookup.list_active_categories(emp) if c.name == "Hardware")
    skill = container.incidents.create_incident(emp, request_for(network, category, "Switch fan noisy", Level.LOW, Level.LOW))
    assert skill.assigned_technician.username == "tech5"          # the only available Hardware technician
    container.admin.set_assignment_strategy(admin, "load_based")
    load = container.incidents.create_incident(emp, request_for(network, category, "Rack door loose", Level.LOW, Level.LOW))
    assert load.assigned_technician.username != "tech5"           # fewest active incidents, skills ignored


def request_for(service, category, title, impact=Level.HIGH, urgency=Level.HIGH):
    from app.ports.dto import CreateIncidentRequest
    return CreateIncidentRequest(title=title, description=f"{title}. Several users are affected.",
                                 category_id=category.id, service_id=service.id,
                                 impact=impact, urgency=urgency, affected_users=40)
