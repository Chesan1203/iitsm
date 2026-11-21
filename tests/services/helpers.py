"""Shared test helpers for the services layer."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.domain.business_rules import BusinessRules
from app.domain.enums import (
    AdminLevel,
    ChannelType,
    IncidentEventType,
    Level,
    NoteType,
    Priority,
)
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.user import Administrator, Employee, Technician, User
from app.domain.strategies.priority import PriorityResult
from app.domain.time_provider import TimeProvider
from app.services.channels.notification_channel import NotificationChannel

T0 = datetime(2026, 11, 14, 10, 0, 0)


class RecordingChannel(NotificationChannel):
    """Remembers who was told what, so tests can compare against the plan's table."""

    def __init__(self):
        self.sent: list[tuple[IncidentEventType, str, str]] = []

    @property
    def channel_type(self):
        return ChannelType.IN_APP

    def send(self, recipient, incident, event_type, message):
        self.sent.append((event_type, recipient.username, message))

    def recipients_of(self, event_type):
        return {name for kind, name, _ in self.sent if kind is event_type}


class ManualTime(TimeProvider):
    """A clock the test controls: set `current`, or call advance()."""

    def __init__(self, current: datetime = T0):
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance(self, minutes: float) -> None:
        self.current += timedelta(minutes=minutes)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def default_policy() -> SlaPolicy:
    return SlaPolicy("Default", True, {p: SlaTarget(*m) for p, m in
                                       BusinessRules.DEFAULT_SLA_TARGET_MINUTES.items()})


def make_world(repos) -> SimpleNamespace:
    """Save a small cast and return it. `repos` is anything with the repository attributes
    (FakeRepositories, or the SQLite bundle)."""
    r = repos
    return SimpleNamespace(
        repos=r,
        reporter=r.users.save(Employee("emp1", "Asha Rao", "emp1@x.com", "hash", "Finance")),
        other_employee=r.users.save(Employee("emp2", "Bala S", "emp2@x.com", "hash", "Sales")),
        tech=r.users.save(Technician("tech1", "Ravi K", "tech1@x.com", "hash", {"Database"}, 4)),
        tech2=r.users.save(Technician("tech2", "Priya M", "tech2@x.com", "hash", {"Network"}, 6)),
        admin=r.users.save(Administrator("admin1", "Meera N", "admin1@x.com", "hash", AdminLevel.TEAM_LEAD)),
        sysadmin=r.users.save(Administrator("admin2", "Karthik I", "admin2@x.com", "hash", AdminLevel.SYSTEM_ADMIN)),
        manager=r.users.save(Administrator("admin3", "Sunita R", "admin3@x.com", "hash", AdminLevel.IT_MANAGER)),
        category=r.categories.save(Category("Database", "DB issues", "Database")),
        service=r.services.save(ITService("Payment", "Payments", Level.HIGH)),
        policy=r.policies.save(default_policy()),
    )


def new_incident(w, title="Payment down", description="Cannot pay", created_at=T0,
                 reporter: User | None = None) -> Incident:
    return w.repos.incidents.save(Incident(
        title, description, reporter or w.reporter, w.category, w.service,
        Level.HIGH, Level.HIGH, 120, created_at))


def classify(incident: Incident, minutes=1, priority=Priority.P1) -> Incident:
    tracker = SlaTracker(incident.created_at + timedelta(minutes=5),
                         incident.created_at + timedelta(minutes=30))
    incident.classify(User.system(), at(minutes), PriorityResult(27, priority, "3x3x3 = 27"), tracker)
    return incident


def assign(incident: Incident, tech: Technician, minutes=2) -> Incident:
    incident.assign_to(User.system(), at(minutes), tech, 0)
    return incident


# ---- helpers for tests that use the whole service stack (see the `stack` fixture) ---------------

def request(w, title="Payment down", description="Customers cannot pay", **extra):
    from app.ports.dto import CreateIncidentRequest
    base = dict(title=title, description=description, category_id=w.category.id, service_id=w.service.id,
                impact=Level.HIGH, urgency=Level.HIGH, affected_users=120)
    return CreateIncidentRequest(**{**base, **extra})


def create(stack, title="Payment down", actor=None, **extra):
    return stack.svc.create_incident(actor or stack.w.reporter, request(stack.w, title, **extra))


def set_available(stack, user, available):
    loaded = stack.repos.users.find_by_id(user.id)
    loaded.set_available(available)
    stack.repos.users.save(loaded)


def actions(stack, incident):
    return [r.action for r in stack.repos.audits.find_by_incident(incident.id)]


def finish(stack, incident):
    """Walk an assigned incident to CLOSED through the service."""
    w, s = stack.w, stack.svc
    s.acknowledge(w.tech, incident.id)
    s.start_investigation(w.tech, incident.id)
    s.resolve(w.tech, incident.id, "Fixed", "Details")
    s.verify(w.reporter, incident.id)
    return s.close(w.reporter, incident.id)


def run_full_lifecycle(w, incident: Incident) -> Incident:
    t, r = w.tech, incident.reporter
    classify(incident)
    assign(incident, t)
    incident.acknowledge(t, at(3))
    incident.start_investigation(t, at(4))
    incident.add_note(t, at(5), "Checking the pool", NoteType.INVESTIGATION)
    incident.resolve(t, at(8), "Restarted pool", "Pool exhausted")
    incident.verify(r, at(9))
    incident.close(r, at(10))
    return incident
