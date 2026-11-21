"""Fixtures for the persistence tests: a throwaway database file and a few saved users."""
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from app.domain.enums import AdminLevel, Level, NoteType, Priority
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.user import Administrator, Employee, Technician, User
from app.domain.strategies.priority import PriorityResult
from app.persistence.database import Database
from app.persistence.sqlite_audit_repository import SqliteAuditRepository
from app.persistence.sqlite_category_repository import SqliteCategoryRepository
from app.persistence.sqlite_incident_repository import SqliteIncidentRepository
from app.persistence.sqlite_notification_repository import SqliteNotificationRepository
from app.persistence.sqlite_service_repository import SqliteServiceRepository
from app.persistence.sqlite_settings_repository import SqliteSettingsRepository
from app.persistence.sqlite_sla_event_repository import SqliteSlaEventRepository
from app.persistence.sqlite_sla_policy_repository import SqliteSlaPolicyRepository
from app.persistence.sqlite_user_repository import SqliteUserRepository

T0 = datetime(2026, 11, 14, 10, 5)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def new_employee(username="emp1", active=True) -> Employee:
    return Employee(username, "Asha Rao", f"{username}@x.com", "hash-e", "Finance", active=active)


def new_technician(username="tech1", skills=("Database", "Network"), experience=4,
                   available=True, max_workload=5) -> Technician:
    return Technician(username, "Ravi K", f"{username}@x.com", "hash-t", skills, experience,
                      available, max_workload)


def new_admin(username="admin1", level=AdminLevel.TEAM_LEAD) -> Administrator:
    return Administrator(username, "Meera N", f"{username}@x.com", "hash-a", level)


@dataclass
class World:
    """A database plus every repository and a small set of already-saved reference objects."""
    db: Database
    users: SqliteUserRepository
    categories: SqliteCategoryRepository
    services: SqliteServiceRepository
    policies: SqliteSlaPolicyRepository
    incidents: SqliteIncidentRepository
    audits: SqliteAuditRepository
    notifications: SqliteNotificationRepository
    sla_events: SqliteSlaEventRepository
    settings: SqliteSettingsRepository
    reporter: Employee
    technician: Technician
    admin: Administrator
    category: Category
    service: ITService

    def new_incident(self, title="Payment down", description="Cannot pay", created_at=T0,
                     reporter: User | None = None, service: ITService | None = None,
                     impact=Level.HIGH, urgency=Level.HIGH, users=120, save=True) -> Incident:
        incident = Incident(title, description, reporter or self.reporter, self.category,
                            service or self.service, impact, urgency, users, created_at)
        return self.incidents.save(incident) if save else incident

    def classify(self, incident: Incident, priority=Priority.P1, minutes=0) -> Incident:
        tracker = SlaTracker(incident.created_at + timedelta(minutes=5),
                             incident.created_at + timedelta(minutes=30))
        incident.classify(User.system(), at(minutes + 1), PriorityResult(27, priority, "3x3x3"), tracker)
        return incident

    def assign(self, incident: Incident, minutes=0) -> Incident:
        incident.assign_to(User.system(), at(minutes + 2), self.technician, 0)
        return incident

    def run_full_lifecycle(self, incident: Incident) -> Incident:
        """NEW to CLOSED, with notes, a resolution, feedback and an SLA tracker."""
        t, r = self.technician, incident.reporter
        self.classify(incident)
        self.assign(incident)
        incident.acknowledge(t, at(3))
        incident.start_investigation(t, at(4))
        incident.add_note(t, at(5), "Checking the connection pool", NoteType.INVESTIGATION)
        incident.request_info(t, at(6), "Which app version are you on?")
        incident.respond_to_info(r, at(7), "Version 2.3")
        incident.resolve(t, at(8), "Restarted DB pool", "Pool was exhausted")
        incident.verify(r, at(9))
        incident.close(r, at(10))
        incident.submit_feedback(r, at(11), 5, "Fast fix")
        return incident


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "test.db")
    database.initialise()
    return database


@pytest.fixture
def world(db) -> World:
    users, categories, services = (SqliteUserRepository(db), SqliteCategoryRepository(db),
                                   SqliteServiceRepository(db))
    return World(
        db=db, users=users, categories=categories, services=services,
        policies=SqliteSlaPolicyRepository(db), incidents=SqliteIncidentRepository(db),
        audits=SqliteAuditRepository(db), notifications=SqliteNotificationRepository(db),
        sla_events=SqliteSlaEventRepository(db), settings=SqliteSettingsRepository(db),
        reporter=users.save(new_employee()), technician=users.save(new_technician()),
        admin=users.save(new_admin()),
        category=categories.save(Category("Database", "DB issues", "Database")),
        service=services.save(ITService("Payment", "Payments", Level.HIGH)),
    )
