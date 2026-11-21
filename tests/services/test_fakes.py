"""P3 T1: the in-memory fakes. The parity test runs one scenario through the fakes AND the real
SQLite repositories and demands the same answers, so the fakes cannot drift from reality."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.domain.enums import (
    ChannelType,
    IncidentEventType,
    IncidentStatus,
    Priority,
    SlaEventType,
    SlaStatus,
)
from app.domain.exceptions import PersistenceError
from app.domain.models.audit import AuditRecord
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent
from app.persistence.database import Database
from app.persistence.sqlite_audit_repository import SqliteAuditRepository
from app.persistence.sqlite_category_repository import SqliteCategoryRepository
from app.persistence.sqlite_incident_repository import SqliteIncidentRepository
from app.persistence.sqlite_notification_repository import SqliteNotificationRepository
from app.persistence.sqlite_report_repository import SqliteReportRepository
from app.persistence.sqlite_service_repository import SqliteServiceRepository
from app.persistence.sqlite_settings_repository import SqliteSettingsRepository
from app.persistence.sqlite_sla_event_repository import SqliteSlaEventRepository
from app.persistence.sqlite_sla_policy_repository import SqliteSlaPolicyRepository
from app.persistence.sqlite_user_repository import SqliteUserRepository
from app.ports.dto import AuditFilter, IncidentSearchCriteria

from .fakes import FakeRepositories
from .helpers import assign, at, classify, make_world, new_incident, run_full_lifecycle


def sqlite_repos(tmp_path) -> SimpleNamespace:
    db = Database(tmp_path / "parity.db")
    db.initialise()
    return SimpleNamespace(
        users=SqliteUserRepository(db), categories=SqliteCategoryRepository(db),
        services=SqliteServiceRepository(db), policies=SqliteSlaPolicyRepository(db),
        incidents=SqliteIncidentRepository(db), audits=SqliteAuditRepository(db),
        notifications=SqliteNotificationRepository(db), sla_events=SqliteSlaEventRepository(db),
        settings=SqliteSettingsRepository(db), reports=SqliteReportRepository(db))


# ---- every fake saves and loads ---------------------------------------------------------------------

def test_users_services_categories_policies_round_trip_and_copy():
    w = make_world(FakeRepositories())
    r = w.repos
    loaded = r.users.find_by_id(w.tech.id)
    assert loaded == w.tech and loaded is not w.tech
    assert r.users.find_by_username("emp1") == w.reporter
    assert [u.username for u in r.users.find_by_role(w.tech.role)] == ["tech1", "tech2"]
    assert r.users.find_admins_by_level(w.admin.admin_level) == [w.admin]
    assert r.services.find_by_id(w.service.id) == w.service and r.services.exists_by_name("payment")
    assert r.categories.find_by_id(w.category.id) == w.category
    assert r.policies.find_default() == w.policy and r.policies.find_all() == [w.policy]
    assert r.users.find_by_id(999) is None and r.services.find_by_id(999) is None


def test_changes_to_a_loaded_object_are_not_stored_until_saved():
    w = make_world(FakeRepositories())
    loaded = w.repos.users.find_by_id(w.tech.id)
    loaded.set_available(False)
    assert w.repos.users.find_by_id(w.tech.id).available is True
    w.repos.users.save(loaded)
    assert w.repos.users.find_by_id(w.tech.id).available is False


def test_duplicate_names_and_missing_ids_are_rejected_like_the_database():
    from app.domain.models.user import Employee
    w = make_world(FakeRepositories())
    with pytest.raises(PersistenceError):
        w.repos.users.save(Employee("emp1", "Dup", "d@x.com", "h"))
    with pytest.raises(PersistenceError):
        w.repos.users.save(Employee("ghost", "G", "g@x.com", "h", id=999))


def test_incident_fake_assigns_tickets_loses_observers_and_sees_fresh_users():
    w = make_world(FakeRepositories())
    first, second = new_incident(w, "One"), new_incident(w, "Two")
    assert (first.ticket_number, second.ticket_number) == ("INC-1001", "INC-1002")
    loaded = w.repos.incidents.find_by_id(first.id)
    assert loaded._observers == [] and loaded is not first
    deactivated = w.repos.users.find_by_id(w.reporter.id)
    deactivated.deactivate()
    w.repos.users.save(deactivated)
    assert w.repos.incidents.find_by_id(first.id).reporter.active is False   # looked up fresh
    assert w.repos.incidents.find_by_ticket("INC-1002").title == "Two"
    assert w.repos.incidents.find_by_id(999) is None


def test_audit_notification_sla_event_and_settings_fakes():
    w = make_world(FakeRepositories())
    r = w.repos
    saved = r.audits.save(AuditRecord(incident_id=1, ticket_number="INC-1001", timestamp=at(1),
                                      actor_id=0, actor_name="System", action="CREATED"))
    assert saved.id == 1 and r.audits.find_by_incident(1) == [saved]
    note = r.notifications.save(Notification(recipient_id=w.reporter.id, incident_id=1,
                                             event_type=IncidentEventType.CREATED, channel=ChannelType.IN_APP,
                                             message="hi", created_at=at(1)))
    assert r.notifications.count_unread(w.reporter.id) == 1
    r.notifications.mark_read(note.id)
    assert r.notifications.count_unread(w.reporter.id) == 0
    event = SlaEvent(incident_id=1, event_type=SlaEventType.RESPONSE_WARNING, recorded_at=at(4))
    r.sla_events.save(event)
    assert r.sla_events.exists(1, SlaEventType.RESPONSE_WARNING)
    with pytest.raises(PersistenceError):
        r.sla_events.save(event)
    assert r.settings.get("k") is None and r.settings.get("k", "d") == "d"
    r.settings.put("k", "v")
    assert r.settings.get("k") == "v"


# ---- parity with the real SQLite repositories --------------------------------------------------------

def _scenario(repos):
    w = make_world(repos)
    a = classify(new_incident(w, "Payment gateway down", "Users cannot pay", at(0)))
    repos.incidents.save(a)
    b = assign(classify(new_incident(w, "VPN slow", "Remote access is slow", at(60)), 61, Priority.P4), w.tech, 62)
    repos.incidents.save(b)
    c = run_full_lifecycle(w, new_incident(w, "Printer jam", "Third floor printer", at(60 * 24 * 3)))
    repos.incidents.save(c)
    d = new_incident(w, "Other person's issue", "Different reporter", at(90), reporter=w.other_employee)
    for incident, kind in ((a, SlaEventType.RESPONSE_VIOLATED), (b, SlaEventType.RESPONSE_WARNING),
                           (c, SlaEventType.RESOLUTION_VIOLATED)):
        repos.sla_events.save(SlaEvent(incident_id=incident.id, event_type=kind, recorded_at=at(70)))
    return w, (a, b, c, d)


def _observe(repos, w):
    """Everything the services will ask the repositories, as plain comparable values."""
    def view(items):
        return [(i.ticket_number, i.status, i.priority, i.title) for i in items]
    inc = repos.incidents
    since = at(0)
    searches = {
        "all": IncidentSearchCriteria(),
        "status": IncidentSearchCriteria(status=IncidentStatus.ASSIGNED),
        "priority": IncidentSearchCriteria(priority=Priority.P1),
        "reporter": IncidentSearchCriteria(reporter_id=w.other_employee.id),
        "technician": IncidentSearchCriteria(technician_id=w.tech.id),
        "keyword": IncidentSearchCriteria(keyword="PAY"),
        "day": IncidentSearchCriteria(from_date=date(2026, 11, 14), to_date=date(2026, 11, 14)),
        "sla": IncidentSearchCriteria(sla_status=SlaStatus.ON_TRACK),
        "none": IncidentSearchCriteria(keyword="zzz"),
    }
    out = {name: view(inc.search(c)) for name, c in searches.items()}
    out["open"] = view(inc.find_open())
    out["unack"] = view(inc.find_unacknowledged())
    out["recent_service"] = view(inc.find_recent_by_service(w.service.id, since))
    out["recent_reporter"] = view(inc.find_recent_by_reporter(w.other_employee.id, since))
    out["active"] = inc.count_active_by_technician(w.tech.id)
    out["resolved_on_service"] = inc.count_resolved_by_technician_on_service(w.tech.id, w.service.id)
    reports = repos.reports
    out["overview"] = reports.get_overview()
    out["workload"] = reports.get_technician_workload()
    out["services"] = reports.get_service_analysis()
    out["categories"] = reports.get_category_analysis()
    out["violations"] = [(v.ticket_number, v.priority, v.technician_name, v.event_type)
                         for v in reports.get_sla_violations()]
    return out


def test_fakes_give_the_same_answers_as_the_sqlite_repositories(tmp_path):
    fake, real = FakeRepositories(), sqlite_repos(tmp_path)
    fake_world, _ = _scenario(fake)
    real_world, _ = _scenario(real)
    observed_fake, observed_real = _observe(fake, fake_world), _observe(real, real_world)
    for name in observed_real:
        assert observed_fake[name] == observed_real[name], name
    assert observed_real["overview"].total == 4          # the scenario really produced data
    assert len(observed_real["all"]) == 4 and observed_real["none"] == []


def test_audit_search_parity(tmp_path):
    for repos in (FakeRepositories(), sqlite_repos(tmp_path)):
        make_world(repos)
        for minutes, action in ((1, "CREATED"), (2, "ASSIGNED"), (3, "CREATED")):
            repos.audits.save(AuditRecord(incident_id=1, ticket_number="INC-1001", timestamp=at(minutes),
                                          actor_id=0, actor_name="System", action=action))
        assert [r.action for r in repos.audits.search(AuditFilter(action="CREATED"))] == ["CREATED", "CREATED"]
        assert [r.timestamp for r in repos.audits.search(AuditFilter(incident_id=1))] == [at(3), at(2), at(1)]
        assert [r.action for r in repos.audits.find_by_incident(1)] == ["CREATED", "ASSIGNED", "CREATED"]
