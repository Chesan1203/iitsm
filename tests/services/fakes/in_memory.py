"""In-memory stand-ins for every repository interface (plan T1).

They behave like the SQLite repositories where it matters for the services:
  * objects are copied on the way in and out, so changing an object you loaded does nothing
    until you save it
  * an incident is stored as a snapshot and rebuilt with Incident.restore, so observers are
    lost on load (the services must re-attach them) and users/services/categories are looked up
    fresh by id, like the real JOINs
  * ids and INC-1001 style ticket numbers are assigned on first save
  * search, recent-incident queries and counts follow the same rules as the SQL
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time, timedelta

from app.domain.enums import (
    AdminLevel,
    IncidentStatus,
    Priority,
    Role,
    SlaEventType,
)
from app.domain.exceptions import PersistenceError
from app.domain.models.audit import AuditRecord
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent, SlaPolicy
from app.domain.models.user import User
from app.ports.dto import (
    AuditFilter,
    CountRow,
    IncidentSearchCriteria,
    OverviewReport,
    SlaViolationRow,
    WorkloadRow,
)
from app.ports.repositories import (
    AuditRepository,
    CategoryRepository,
    IncidentRepository,
    NotificationRepository,
    ReportRepository,
    ServiceRepository,
    SettingsRepository,
    SlaEventRepository,
    SlaPolicyRepository,
    UserRepository,
)

_ACTIVE = {IncidentStatus.ASSIGNED, IncidentStatus.ACKNOWLEDGED, IncidentStatus.IN_PROGRESS}
_FINISHED = {IncidentStatus.RESOLVED, IncidentStatus.VERIFIED, IncidentStatus.CLOSED}
_VIOLATIONS = {SlaEventType.RESPONSE_VIOLATED, SlaEventType.RESOLUTION_VIOLATED}
SEARCH_LIMIT = 500


class _EntityStore:
    """Shared save/find logic for objects that have an id (users, services, categories...)."""

    def __init__(self):
        self._items: dict[int, object] = {}
        self._next_id = 1

    def _save(self, item):
        if item.id is None:
            item.assign_id(self._next_id)
            self._next_id += 1
        elif item.id not in self._items:
            raise PersistenceError(f"{type(item).__name__} {item.id} does not exist")
        self._items[item.id] = copy.deepcopy(item)
        return item

    def _get(self, id):
        item = self._items.get(id)
        return None if item is None else copy.deepcopy(item)

    def _all(self):
        return [copy.deepcopy(self._items[i]) for i in sorted(self._items)]


class FakeUserRepository(_EntityStore, UserRepository):
    def save(self, user: User) -> User:
        if user.is_system:
            raise PersistenceError("The system user is never stored")
        clash = next((u for u in self._items.values()
                      if u.username == user.username and u.id != user.id), None)
        if clash is not None:
            raise PersistenceError("UNIQUE constraint failed: users.username")
        return self._save(user)

    def find_by_id(self, id: int) -> User | None:
        return self._get(id)

    def find_by_username(self, username: str) -> User | None:
        return next((copy.deepcopy(u) for u in self._items.values() if u.username == username), None)

    def find_all(self) -> list[User]:
        return self._all()

    def find_by_role(self, role: Role) -> list[User]:
        return [u for u in self._all() if u.role is role]

    def find_admins_by_level(self, level: AdminLevel) -> list[User]:
        return [u for u in self.find_by_role(Role.ADMINISTRATOR) if u.admin_level is level]


class FakeServiceRepository(_EntityStore, ServiceRepository):
    def save(self, service: ITService) -> ITService:
        if any(s.name == service.name and s.id != service.id for s in self._items.values()):
            raise PersistenceError("UNIQUE constraint failed: it_services.name")
        return self._save(service)

    def find_by_id(self, id: int) -> ITService | None:
        return self._get(id)

    def find_all(self) -> list[ITService]:
        return self._all()

    def exists_by_name(self, name: str) -> bool:
        return any(s.name.lower() == name.lower() for s in self._items.values())


class FakeCategoryRepository(_EntityStore, CategoryRepository):
    def save(self, category: Category) -> Category:
        if any(c.name == category.name and c.id != category.id for c in self._items.values()):
            raise PersistenceError("UNIQUE constraint failed: categories.name")
        return self._save(category)

    def find_by_id(self, id: int) -> Category | None:
        return self._get(id)

    def find_all(self) -> list[Category]:
        return self._all()


class FakeSlaPolicyRepository(_EntityStore, SlaPolicyRepository):
    def save(self, policy: SlaPolicy) -> SlaPolicy:
        return self._save(policy)

    def find_by_id(self, id: int) -> SlaPolicy | None:
        return self._get(id)

    def find_default(self) -> SlaPolicy | None:
        return next((p for p in self._all() if p.is_default), None)

    def find_all(self) -> list[SlaPolicy]:
        return self._all()


class FakeSettingsRepository(SettingsRepository):
    def __init__(self):
        self._values: dict[str, str] = {}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._values.get(key, default)

    def put(self, key: str, value: str) -> None:
        self._values[key] = value


class FakeIncidentRepository(IncidentRepository):
    def __init__(self, users: FakeUserRepository, categories: FakeCategoryRepository,
                 services: FakeServiceRepository):
        self._users, self._categories, self._services = users, categories, services
        self._rows: dict[int, object] = {}
        self._next_id = 1

    # ---- save / load ----------------------------------------------------------
    def save(self, incident: Incident) -> Incident:
        if incident.id is None:
            incident.assign_identity(self._next_id, f"INC-{1000 + self._next_id}")
            self._next_id += 1
        elif incident.id not in self._rows:
            raise PersistenceError(f"Incident {incident.id} does not exist")
        self._rows[incident.id] = copy.deepcopy(incident.snapshot())
        return incident

    def _rebuild(self, snapshot) -> Incident:
        """Like the SQL JOINs: current users, service and category are looked up by id."""
        s = copy.deepcopy(snapshot)
        users = self._users
        notes = tuple(replace(n, author=users.find_by_id(n.author.id)) for n in s.notes)
        resolution = (None if s.resolution is None else
                      replace(s.resolution, resolved_by=users.find_by_id(s.resolution.resolved_by.id)))
        return Incident.restore(replace(
            s, reporter=users.find_by_id(s.reporter.id),
            category=self._categories.find_by_id(s.category.id),
            affected_service=self._services.find_by_id(s.affected_service.id),
            assigned_technician=(None if s.assigned_technician is None
                                 else users.find_by_id(s.assigned_technician.id)),
            notes=notes, resolution=resolution))

    def _matching(self, predicate=lambda s: True) -> list[Incident]:
        return [self._rebuild(self._rows[i]) for i in sorted(self._rows) if predicate(self._rows[i])]

    def all_incidents(self) -> list[Incident]:
        return self._matching()

    def find_by_id(self, id: int) -> Incident | None:
        return self._rebuild(self._rows[id]) if id in self._rows else None

    def find_by_ticket(self, ticket_number: str) -> Incident | None:
        found = self._matching(lambda s: s.ticket_number == ticket_number)
        return found[0] if found else None

    # ---- lists -------------------------------------------------------------------
    def search(self, criteria: IncidentSearchCriteria) -> list[Incident]:
        c = criteria

        def ok(s) -> bool:
            if c.ticket_number is not None and s.ticket_number != c.ticket_number:
                return False
            if c.status is not None and s.status is not c.status:
                return False
            if c.priority is not None and s.priority is not c.priority:
                return False
            if c.category_id is not None and s.category.id != c.category_id:
                return False
            if c.service_id is not None and s.affected_service.id != c.service_id:
                return False
            if c.technician_id is not None and (s.assigned_technician is None
                                                or s.assigned_technician.id != c.technician_id):
                return False
            if c.reporter_id is not None and s.reporter.id != c.reporter_id:
                return False
            if c.sla_status is not None and (s.sla_tracker is None or s.sla_tracker.status is not c.sla_status):
                return False
            if c.from_date is not None and s.created_at < _start(c.from_date):
                return False
            if c.to_date is not None and s.created_at >= _start(c.to_date) + timedelta(days=1):
                return False
            if c.keyword is not None and c.keyword.strip():
                word = c.keyword.strip().lower()
                if word not in s.title.lower() and word not in s.description.lower():
                    return False
            return True

        found = self._matching(ok)
        found.sort(key=lambda i: (i.created_at, i.id), reverse=True)
        return found[:SEARCH_LIMIT]

    def find_open(self) -> list[Incident]:
        return self._matching(lambda s: s.status is not IncidentStatus.CLOSED)

    def find_unacknowledged(self) -> list[Incident]:
        return self._matching(lambda s: s.status is IncidentStatus.ASSIGNED)

    def find_recent_by_service(self, service_id: int, since: datetime) -> list[Incident]:
        return self._matching(lambda s: s.affected_service.id == service_id and s.created_at >= since)

    def find_recent_by_reporter(self, reporter_id: int, since: datetime) -> list[Incident]:
        return self._matching(lambda s: s.reporter.id == reporter_id and s.created_at >= since)

    def count_active_by_technician(self, technician_id: int) -> int:
        return len(self._matching(lambda s: s.status in _ACTIVE and s.assigned_technician is not None
                                  and s.assigned_technician.id == technician_id))

    def count_resolved_by_technician_on_service(self, technician_id: int, service_id: int) -> int:
        return len(self._matching(lambda s: s.status in _FINISHED and s.assigned_technician is not None
                                  and s.assigned_technician.id == technician_id
                                  and s.affected_service.id == service_id))


def _start(day: date) -> datetime:
    return datetime.combine(day.date() if isinstance(day, datetime) else day, time.min)


class FakeAuditRepository(AuditRepository):
    def __init__(self):
        self._records: list[AuditRecord] = []

    def save(self, record: AuditRecord) -> AuditRecord:
        saved = replace(record, id=len(self._records) + 1)
        self._records.append(saved)
        return saved

    def find_by_incident(self, incident_id: int) -> list[AuditRecord]:
        return sorted((r for r in self._records if r.incident_id == incident_id),
                      key=lambda r: (r.timestamp, r.id))

    def search(self, audit_filter: AuditFilter) -> list[AuditRecord]:
        f = audit_filter

        def ok(r: AuditRecord) -> bool:
            return ((f.incident_id is None or r.incident_id == f.incident_id)
                    and (f.actor_id is None or r.actor_id == f.actor_id)
                    and (f.action is None or r.action == f.action)
                    and (f.from_date is None or r.timestamp >= _start(f.from_date))
                    and (f.to_date is None or r.timestamp < _start(f.to_date) + timedelta(days=1)))
        return sorted((r for r in self._records if ok(r)),
                      key=lambda r: (r.timestamp, r.id), reverse=True)[:SEARCH_LIMIT]


class FakeNotificationRepository(NotificationRepository):
    def __init__(self):
        self._items: dict[int, Notification] = {}

    def save(self, notification: Notification) -> Notification:
        if notification.id is None:
            notification = replace(notification, id=len(self._items) + 1)
        self._items[notification.id] = notification
        return notification

    def get(self, notification_id: int) -> Notification | None:
        return self._items.get(notification_id)

    def find_by_recipient(self, user_id: int, limit: int) -> list[Notification]:
        mine = [n for n in self._items.values() if n.recipient_id == user_id]
        mine.sort(key=lambda n: (n.created_at, n.id), reverse=True)
        return mine[:max(0, limit)]

    def count_unread(self, user_id: int) -> int:
        return sum(1 for n in self._items.values() if n.recipient_id == user_id and not n.is_read)

    def mark_read(self, notification_id: int) -> None:
        if notification_id in self._items:
            self._items[notification_id] = replace(self._items[notification_id], is_read=True)

    def mark_all_read(self, user_id: int) -> None:
        for i, n in list(self._items.items()):
            if n.recipient_id == user_id:
                self._items[i] = replace(n, is_read=True)

    def all(self) -> list[Notification]:
        return [self._items[i] for i in sorted(self._items)]


class FakeSlaEventRepository(SlaEventRepository):
    def __init__(self):
        self._events: list[SlaEvent] = []

    def save(self, event: SlaEvent) -> SlaEvent:
        if self.exists(event.incident_id, event.event_type):
            raise PersistenceError("UNIQUE constraint failed: sla_events.incident_id, sla_events.event_type")
        saved = replace(event, id=len(self._events) + 1)
        self._events.append(saved)
        return saved

    def find_by_incident(self, incident_id: int) -> list[SlaEvent]:
        return sorted((e for e in self._events if e.incident_id == incident_id),
                      key=lambda e: (e.recorded_at, e.id))

    def exists(self, incident_id: int, event_type: SlaEventType) -> bool:
        return any(e.incident_id == incident_id and e.event_type is event_type for e in self._events)

    def all(self) -> list[SlaEvent]:
        return list(self._events)


class FakeReportRepository(ReportRepository):
    """Computes the same numbers as the SQL reports from the other fakes."""

    def __init__(self, incidents: FakeIncidentRepository, users: FakeUserRepository,
                 services: FakeServiceRepository, categories: FakeCategoryRepository,
                 sla_events: FakeSlaEventRepository):
        self._incidents, self._users, self._services = incidents, users, services
        self._categories, self._events = categories, sla_events

    def get_overview(self) -> OverviewReport:
        incidents = self._incidents.all_incidents()
        unfinished = [i for i in incidents if i.status not in _FINISHED]
        violated = {e.incident_id for e in self._events.all() if e.event_type in _VIOLATIONS}
        return OverviewReport(
            total=len(incidents), open=len(unfinished),
            critical_open=sum(1 for i in unfinished if i.priority is Priority.P1),
            resolved=len(incidents) - len(unfinished), sla_violations=len(violated))

    def get_technician_workload(self) -> list[WorkloadRow]:
        incidents = self._incidents.all_incidents()
        rows = [WorkloadRow(t.id, t.full_name,
                            sum(1 for i in incidents if i.status in _ACTIVE
                                and i.assigned_technician and i.assigned_technician.id == t.id),
                            t.max_workload)
                for t in self._users.find_by_role(Role.TECHNICIAN)]
        return sorted(rows, key=lambda r: (-r.active_count, r.technician_name, r.technician_id))

    def get_service_analysis(self) -> list[CountRow]:
        return self._counts(self._services.find_all(), lambda i: i.affected_service.id)

    def get_category_analysis(self) -> list[CountRow]:
        return self._counts(self._categories.find_all(), lambda i: i.category.id)

    def _counts(self, things, key) -> list[CountRow]:
        incidents = self._incidents.all_incidents()
        rows = [CountRow(t.name, sum(1 for i in incidents if key(i) == t.id)) for t in things]
        return sorted(rows, key=lambda r: (-r.count, r.label))

    def get_sla_violations(self) -> list[SlaViolationRow]:
        rows = []
        for event in self._events.all():
            if event.event_type not in _VIOLATIONS:
                continue
            incident = self._incidents.find_by_id(event.incident_id)
            tech = incident.assigned_technician
            rows.append(((event.recorded_at, event.id),
                         SlaViolationRow(incident.ticket_number, incident.title, incident.priority,
                                         None if tech is None else tech.full_name,
                                         event.event_type, event.recorded_at)))
        # newest first; equal times: highest event id first (same as the SQL ORDER BY)
        return [row for _, row in sorted(rows, key=lambda pair: pair[0], reverse=True)]


class FakeRepositories:
    """All fakes wired together, ready to hand to services."""

    def __init__(self):
        self.users = FakeUserRepository()
        self.categories = FakeCategoryRepository()
        self.services = FakeServiceRepository()
        self.policies = FakeSlaPolicyRepository()
        self.settings = FakeSettingsRepository()
        self.incidents = FakeIncidentRepository(self.users, self.categories, self.services)
        self.audits = FakeAuditRepository()
        self.notifications = FakeNotificationRepository()
        self.sla_events = FakeSlaEventRepository()
        self.reports = FakeReportRepository(self.incidents, self.users, self.services,
                                            self.categories, self.sla_events)
