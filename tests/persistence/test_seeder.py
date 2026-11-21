"""P2 T6: the demo data seeder. Checked against the real domain engines, not hand-copied numbers."""
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import pytest

from app.domain.business_rules import BusinessRules
from app.domain.enums import (
    AdminLevel, EscalationLevel, IncidentStatus as S, Priority, Role, SlaStatus,
)
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.intelligence.duplicate_detector import DuplicateDetector
from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.time_provider import TimeProvider
from app.persistence.database import Database
from app.persistence.seeder import DemoDataSeeder
from app.persistence.sqlite_audit_repository import SqliteAuditRepository
from app.persistence.sqlite_category_repository import SqliteCategoryRepository
from app.persistence.sqlite_incident_repository import SqliteIncidentRepository
from app.persistence.sqlite_notification_repository import SqliteNotificationRepository
from app.persistence.sqlite_report_repository import SqliteReportRepository
from app.persistence.sqlite_service_repository import SqliteServiceRepository
from app.persistence.sqlite_sla_event_repository import SqliteSlaEventRepository
from app.persistence.sqlite_sla_policy_repository import SqliteSlaPolicyRepository
from app.persistence.sqlite_user_repository import SqliteUserRepository
from app.ports.dto import AuditFilter, IncidentSearchCriteria

NOW = datetime(2026, 11, 16, 12, 0, 0)


class FixedTime(TimeProvider):
    def now(self) -> datetime:
        return NOW


@dataclass
class Env:
    db: Database
    users: SqliteUserRepository
    categories: SqliteCategoryRepository
    services: SqliteServiceRepository
    policies: SqliteSlaPolicyRepository
    incidents: SqliteIncidentRepository
    audits: SqliteAuditRepository
    notifications: SqliteNotificationRepository
    sla_events: SqliteSlaEventRepository
    seeder: DemoDataSeeder

    def all_incidents(self):
        return self.incidents.search(IncidentSearchCriteria())

    def by_title(self, title):
        return next(i for i in self.all_incidents() if i.title == title)


def build_env(tmp_path, password_hash=None) -> Env:
    db = Database(tmp_path / "seed.db")
    db.initialise()
    repos = dict(users=SqliteUserRepository(db), categories=SqliteCategoryRepository(db),
                 services=SqliteServiceRepository(db), policies=SqliteSlaPolicyRepository(db),
                 incidents=SqliteIncidentRepository(db), audits=SqliteAuditRepository(db),
                 notifications=SqliteNotificationRepository(db), sla_events=SqliteSlaEventRepository(db))
    seeder = DemoDataSeeder(*repos.values(), time_provider=FixedTime(), password_hash=password_hash)
    return Env(db=db, seeder=seeder, **repos)


@pytest.fixture(scope="module")
def env(tmp_path_factory) -> Env:
    """Seeded once and shared: every test here only reads."""
    e = build_env(tmp_path_factory.mktemp("seed"))
    assert e.seeder.seed_if_empty() is True
    return e


# ---- shape of the data -----------------------------------------------------------------------

def test_people_and_reference_counts(env):
    roles = Counter(u.role for u in env.users.find_all())
    assert roles == {Role.ADMINISTRATOR: 4, Role.TECHNICIAN: 6, Role.EMPLOYEE: 10}
    assert len(env.services.find_all()) == 8
    assert len(env.categories.find_all()) == 9
    assert len(env.policies.find_all()) == 2 and env.policies.find_default().name == "Default"


def test_login_names_and_admin_levels_match_the_readme(env):
    names = {u.username for u in env.users.find_all()}
    assert {f"admin{i}" for i in range(1, 5)} | {f"tech{i}" for i in range(1, 7)} | {f"emp{i}" for i in range(1, 11)} == names
    levels = {u.username: u.admin_level for u in env.users.find_by_role(Role.ADMINISTRATOR)}
    assert levels == {"admin1": AdminLevel.TEAM_LEAD, "admin2": AdminLevel.SYSTEM_ADMIN,
                      "admin3": AdminLevel.IT_MANAGER, "admin4": AdminLevel.SYSTEM_ADMIN}


def test_every_status_has_the_planned_number_of_incidents(env):
    counts = Counter(i.status for i in env.all_incidents())
    assert counts == {S.CLOSED: 21, S.VERIFIED: 3, S.RESOLVED: 4, S.IN_PROGRESS: 8,
                      S.ACKNOWLEDGED: 3, S.ASSIGNED: 4, S.CLASSIFIED: 2}


def test_overview_report_agrees_with_the_data(env):
    overview = SqliteReportRepository(env.db).get_overview()
    incidents = env.all_incidents()
    unfinished = [i for i in incidents if i.status not in (S.RESOLVED, S.VERIFIED, S.CLOSED)]
    assert overview.total == 45 and overview.open == len(unfinished) == 17
    assert overview.resolved == 28
    assert overview.critical_open == sum(1 for i in unfinished if i.priority is Priority.P1) > 0
    assert overview.sla_violations >= 4


def test_all_four_priorities_appear(env):
    assert {i.priority for i in env.all_incidents()} == set(Priority)


def test_data_spans_two_weeks_and_nothing_is_in_the_future(env):
    incidents = env.all_incidents()
    assert min(i.created_at for i in incidents) >= NOW - timedelta(days=14)
    for i in incidents:
        stamps = [i.created_at, i.assigned_at, i.acknowledged_at, i.resolved_at, i.verified_at,
                  i.closed_at, i.sla_tracker.response_deadline if i.sla_tracker else None]
        assert all(t <= NOW + timedelta(days=1) for t in stamps if t)
        assert all(t <= NOW for t in stamps[:6] if t), i.ticket_number


def test_ticket_numbers_rise_with_creation_time(env):
    ordered = sorted(env.all_incidents(), key=lambda i: i.id)
    assert [i.ticket_number for i in ordered][:2] == ["INC-1001", "INC-1002"]
    assert [i.created_at for i in ordered] == sorted(i.created_at for i in ordered)


# ---- consistency with the live engines ----------------------------------------------------------

def test_sla_calculator_finds_nothing_new_so_the_scheduler_will_not_repeat_events(env):
    calculator = SlaCalculator()
    for i in env.all_incidents():
        if i.sla_tracker is None:
            continue
        result = calculator.evaluate(i, NOW)
        assert result.new_events == [], i.ticket_number
        assert result.status is i.sla_tracker.status, i.ticket_number


def test_violated_incidents_have_matching_sla_event_rows(env):
    violated = [i for i in env.all_incidents() if i.sla_tracker and i.sla_tracker.status is SlaStatus.VIOLATED]
    assert len(violated) >= 4
    for i in violated:
        assert env.sla_events.find_by_incident(i.id), i.ticket_number
    assert any(i.sla_tracker.status is SlaStatus.WARNING for i in env.all_incidents() if i.sla_tracker)


def test_closed_and_resolved_incidents_are_fully_filled_in(env):
    for i in env.all_incidents():
        if i.status in (S.RESOLVED, S.VERIFIED, S.CLOSED):
            assert i.resolution and i.resolved_at and i.assigned_technician and i.acknowledged_at
        if i.status in (S.VERIFIED, S.CLOSED):
            assert i.verified_at
        if i.status is S.CLOSED:
            assert i.closed_at
    assert any(i.feedback for i in env.all_incidents())
    assert any(n.note_type.name == "INFO_REQUEST" for i in env.all_incidents() for n in i.notes)


def test_technician_workload_respects_limits_and_leave(env):
    rows = {r.technician_name: r for r in SqliteReportRepository(env.db).get_technician_workload()}
    assert len(rows) == 6
    assert all(r.active_count <= r.max_workload for r in rows.values())
    assert rows["Lakshmi Rao"].active_count == 0            # tech6 is on leave
    assert sum(r.active_count for r in rows.values()) == 15  # 8 + 3 + 4 open and active


def test_cloud_incidents_stay_classified_because_no_cloud_technician_is_free(env):
    cloud = [i for i in env.all_incidents() if i.category.name == "Cloud" and i.is_open and i.status in (S.CLASSIFIED,)]
    assert len(cloud) == 2 and all(i.assigned_technician is None for i in cloud)


# ---- planted demo scenarios --------------------------------------------------------------------------

def test_three_payment_sentences_flag_each_other_as_duplicates(env):
    trio = [env.by_title(t) for t in ("Payment application unavailable",
                                      "Payment transaction failing", "Unable to make payment")]
    detector = DuplicateDetector()
    for incident in trio:
        others = [o for o in trio if o is not incident]
        assert {m.other_ticket_number for m in detector.find_similar(incident, others)} == {o.ticket_number for o in others}
    assert trio[0].possible_duplicate_of is None
    assert trio[1].possible_duplicate_of == trio[2].possible_duplicate_of == trio[0].ticket_number


def test_an_unrelated_incident_is_not_flagged_against_the_payment_ones(env):
    unrelated = env.by_title("Wifi dead zone in building B")
    payment = env.by_title("Payment application unavailable")
    assert DuplicateDetector().find_similar(unrelated, [payment]) == []


def test_three_network_incidents_form_the_only_probable_service_problem(env):
    groups = CorrelationDetector().find_groups(env.incidents.find_open(), NOW)
    probable = [g for g in groups if g.is_probable_service_problem]
    assert len(probable) == 1 and probable[0].service.name == "Network"
    assert len(probable[0].incidents) == 3


def test_exactly_one_p1_is_waiting_to_escalate_and_it_escalates_on_the_10_minute_steps(env):
    policy, waiting = EscalationPolicy(), env.incidents.find_unacknowledged()
    assert policy.evaluate(env.by_title("Primary database cluster unreachable"), NOW) is None  # not overdue yet
    assert [i for i in waiting if policy.evaluate(i, NOW)] == []
    target = env.by_title("Primary database cluster unreachable")
    assert target.status is S.ASSIGNED and target.priority is Priority.P1
    assert NOW - target.assigned_at == timedelta(minutes=1)
    # a few minutes later the response deadline (5 min after creation) has passed
    assert policy.evaluate(target, NOW + timedelta(minutes=4)).new_level is EscalationLevel.TEAM_LEAD
    assert policy.evaluate(target, NOW + timedelta(minutes=14)).new_level is EscalationLevel.SYSTEM_ADMIN
    assert policy.evaluate(target, NOW + timedelta(minutes=24)).new_level is EscalationLevel.IT_MANAGER
    later = NOW + timedelta(minutes=14)
    assert [i.title for i in waiting if policy.evaluate(i, later)] == ["Primary database cluster unreachable"]


# ---- audit trail and notifications -----------------------------------------------------------------------

def test_every_incident_has_an_audit_trail_starting_with_creation(env):
    for i in env.all_incidents():
        trail = env.audits.find_by_incident(i.id)
        assert trail and trail[0].action == "CREATED" and trail[0].ticket_number == i.ticket_number
        assert [r.timestamp for r in trail] == sorted(r.timestamp for r in trail)


def test_a_closed_incident_trail_walks_the_whole_lifecycle(env):
    closed = env.by_title("Email delivery delayed for finance team")
    actions = [r.action for r in env.audits.find_by_incident(closed.id)]
    for step in ("CREATED", "CLASSIFIED", "ASSIGNED", "ACKNOWLEDGED", "INVESTIGATION_STARTED",
                 "RESOLVED", "VERIFIED", "CLOSED"):
        assert step in actions
    assert actions.index("CREATED") < actions.index("ASSIGNED") < actions.index("CLOSED")
    assert env.audits.search(AuditFilter(action="SLA_VIOLATED"))


def test_notifications_exist_for_real_recipients_and_some_are_unread(env):
    user_ids = {u.id for u in env.users.find_all()}
    notes = [n for u in user_ids for n in env.notifications.find_by_recipient(u, 100)]
    assert len(notes) >= 10 and {n.recipient_id for n in notes} <= user_ids
    assert any(not n.is_read for n in notes)
    assert sum(env.notifications.count_unread(u) for u in user_ids) > 0


# ---- running it ------------------------------------------------------------------------------------------

def test_seeding_twice_changes_nothing(env):
    before = (len(env.all_incidents()), len(env.users.find_all()), len(env.categories.find_all()))
    assert env.seeder.seed_if_empty() is False
    assert (len(env.all_incidents()), len(env.users.find_all()), len(env.categories.find_all())) == before


def test_demo_password_is_hashed_once_and_works_for_every_role(env):
    users = env.users.find_all()
    assert len({u.password_hash for u in users}) == 1      # one bcrypt hash reused for everyone
    for username in ("admin1", "tech1", "emp1"):
        user = env.users.find_by_username(username)
        assert bcrypt.checkpw(BusinessRules.DEMO_PASSWORD.encode(), user.password_hash.encode())


def test_module_can_be_run_on_its_own(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env_vars = {**os.environ, "DATABASE_PATH": str(tmp_path / "cli.db")}
    first = subprocess.run([sys.executable, "-m", "app.persistence.seeder"], cwd=root,
                           env=env_vars, capture_output=True, text=True, check=False)
    assert first.returncode == 0 and "Seeded demo data" in first.stdout, first.stderr
    second = subprocess.run([sys.executable, "-m", "app.persistence.seeder"], cwd=root,
                            env=env_vars, capture_output=True, text=True, check=False)
    assert "nothing changed" in second.stdout
