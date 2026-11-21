"""Stand-in implementations of the six service interfaces (stub mode).

They keep everything in memory (see sample_data.py) and apply the DOMAIN's own incident methods,
so state rules and permission errors behave as in real mode. What they do not do: persist anything,
run background jobs, send real notifications, or use the real priority/assignment strategies.
Incident 999 refuses every action with InvalidStateTransitionError, to test error display.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from app.domain.enums import (
    IncidentEventType, IncidentStatus as S, NoteType, Priority, Role, SlaEventType,
)
from app.domain.exceptions import (
    CategoryNotFoundError, IncidentNotFoundError, InvalidInputError, InvalidLoginError,
    InvalidStateTransitionError, ServiceNotFoundError, TechnicianUnavailableError,
    UnauthorizedOperationError, UserNotFoundError,
)
from app.domain.models.candidates import RankedTechnician
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Administrator, Employee, Technician, User
from app.ports.dto import (
    AuditFilter, CategoryRequest, CountRow, CreateIncidentRequest, CreateUserRequest,
    IncidentSearchCriteria, OverviewReport, RegisterRequest, ServiceRequest, SlaPolicyRequest,
    SlaViolationRow, WorkloadRow,
)
from app.ports.services import (
    AdminService, AuthService, IncidentService, LookupService, NotificationService, ReportService,
)
from app.web.stubs.sample_data import (
    ERROR_INCIDENT_ID, PASSWORD, StubWorld, stub_priority, stub_tracker,
)

_ACTIVE = {S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS}
_FINISHED = {S.RESOLVED, S.VERIFIED, S.CLOSED}
PRIORITY_STRATEGIES = ["weighted_score", "rule_based"]
ASSIGNMENT_STRATEGIES = ["skill_based", "load_based", "weighted_recommendation"]


def _require(actor, *roles: Role) -> User:
    if not isinstance(actor, User) or actor.is_system or not actor.active:
        raise UnauthorizedOperationError("You must be signed in to do this")
    if roles and actor.role not in roles:
        raise UnauthorizedOperationError("This action requires a different role")
    return actor


def _admin(actor) -> User:
    return _require(actor, Role.ADMINISTRATOR)


def _text(value, field: str) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else ""
    if not text:
        raise InvalidInputError(f"{field.replace('_', ' ').capitalize()} is required", field)
    return text


class StubAuthService(AuthService):
    def __init__(self, world: StubWorld):
        self._w = world

    def login(self, username: str, password: str) -> User:
        user = next((u for u in self._w.users.values() if u.username == (username or "").strip()), None)
        if user is None or password != PASSWORD or not user.active:
            raise InvalidLoginError("Invalid username or password")
        return user

    def register_employee(self, request: RegisterRequest) -> User:
        username = _text(request.username, "username")
        _text(request.full_name, "full_name")
        if "@" not in (request.email or ""):
            raise InvalidInputError("Enter a valid email address", "email")
        if len(request.password or "") < 8:
            raise InvalidInputError("Password must be at least 8 characters", "password")
        if any(u.username == username for u in self._w.users.values()):
            raise InvalidInputError("That username is already taken", "username")
        user = Employee(username, request.full_name.strip(), request.email.strip(), "stub-hash",
                        request.department or "", id=self._w.next_user_id)
        self._w.next_user_id += 1
        self._w.users[user.id] = user
        return user

    def get_user(self, user_id: int) -> User | None:
        user = self._w.users.get(user_id)
        return user if user is not None and user.active else None


class StubIncidentService(IncidentService):
    def __init__(self, world: StubWorld):
        self._w = world

    # ---- helpers ------------------------------------------------------------------------------
    def _find(self, incident_id) -> Incident:
        incident = self._w.incidents.get(incident_id) if isinstance(incident_id, int) else None
        if incident is None:
            raise IncidentNotFoundError(f"Incident {incident_id} was not found")
        return incident

    @staticmethod
    def _can_view(actor: User, incident: Incident) -> bool:
        tech = incident.assigned_technician
        return (actor.role is Role.ADMINISTRATOR or incident.reporter.id == actor.id
                or (tech is not None and tech.id == actor.id))

    def _load(self, actor, incident_id) -> Incident:
        user = _require(actor)
        incident = self._find(incident_id)
        if not self._can_view(user, incident):
            raise UnauthorizedOperationError("You are not allowed to view this incident")
        return incident

    def _act(self, actor, incident_id, label: str, change, event=IncidentEventType.NOTE_ADDED, notify=None):
        """Apply a domain method to the stored incident, then record an audit entry."""
        incident = self._load(actor, incident_id)
        if incident.id == ERROR_INCIDENT_ID:
            raise InvalidStateTransitionError(
                f"Stub incident {ERROR_INCIDENT_ID} does not allow '{label}' (used to test error display)")
        before = incident.status
        change(incident, self._w.now())
        self._w.log(incident, actor, label.upper().replace(" ", "_"), before, incident.status, label.capitalize())
        if notify:
            self._w.notify(incident.reporter, incident, event, f"{incident.ticket_number}: {notify}")
        return incident

    def _active_count(self, technician_id: int) -> int:
        return sum(1 for i in self._w.incidents.values() if i.status in _ACTIVE
                   and i.assigned_technician and i.assigned_technician.id == technician_id)

    def _technicians(self) -> list[Technician]:
        return [u for u in self._w.users.values() if isinstance(u, Technician)]

    # ---- creating -------------------------------------------------------------------------------
    def create_incident(self, actor: User, request: CreateIncidentRequest) -> Incident:
        reporter = _require(actor)
        title = _text(request.title, "title")
        description = _text(request.description, "description")
        if not isinstance(request.affected_users, int) or isinstance(request.affected_users, bool) or request.affected_users < 1:
            raise InvalidInputError("Affected users must be a whole number of at least 1", "affected_users")
        service = self._w.services.get(request.service_id)
        if service is None or not service.active:
            raise ServiceNotFoundError("The selected service was not found")
        category = self._w.categories.get(request.category_id)
        if category is None or not category.active:
            raise CategoryNotFoundError("The selected category was not found")
        now = self._w.now()
        priority, score = stub_priority(request.impact, request.urgency, service.business_criticality, request.affected_users)
        technician = next((t for t in self._technicians() if t.available and category.required_skill in t.skills
                           and self._active_count(t.id) < t.max_workload), None)
        words = set(title.lower().split())
        duplicate = next((i.ticket_number for i in self._w.incidents.values() if i.is_open
                          and i.affected_service.id == service.id and len(words & set(i.title.lower().split())) >= 2), None)
        iid = self._w.next_incident_id
        self._w.next_incident_id += 1
        incident = Incident.restore(IncidentSnapshot(
            id=iid, ticket_number=f"INC-{1000 + iid}", title=title, description=description, reporter=reporter,
            category=category, affected_service=service, impact=request.impact, urgency=request.urgency,
            affected_users=request.affected_users, priority=priority, priority_score=score,
            status=S.ASSIGNED if technician else S.CLASSIFIED, created_at=now, assigned_technician=technician,
            assigned_at=now if technician else None, possible_duplicate_of=duplicate,
            sla_tracker=stub_tracker(priority, now)))
        self._w.incidents[iid] = incident
        self._w.log(incident, reporter, "CREATED", None, S.NEW, f"Incident created by {reporter.full_name}")
        self._w.log(incident, reporter, "CLASSIFIED", S.NEW, S.CLASSIFIED, f"Priority {priority.name} (score {score})")
        if technician:
            self._w.log(incident, reporter, "ASSIGNED", S.CLASSIFIED, S.ASSIGNED, f"Assigned to {technician.full_name}")
            self._w.notify(technician, incident, IncidentEventType.ASSIGNED, f"{incident.ticket_number} was assigned to you")
        return incident

    # ---- reading ---------------------------------------------------------------------------------
    def get_incident(self, actor: User, incident_id: int) -> Incident:
        return self._load(actor, incident_id)

    def search(self, actor: User, criteria: IncidentSearchCriteria) -> list[Incident]:
        user = _require(actor)
        c = criteria
        found = []
        for i in self._w.incidents.values():
            if user.role is Role.EMPLOYEE and i.reporter.id != user.id:
                continue
            if user.role is Role.TECHNICIAN and not (i.assigned_technician and i.assigned_technician.id == user.id):
                continue
            if c.ticket_number and i.ticket_number != c.ticket_number:
                continue
            if c.status and i.status is not c.status:
                continue
            if c.priority and i.priority is not c.priority:
                continue
            if c.category_id and i.category.id != c.category_id:
                continue
            if c.service_id and i.affected_service.id != c.service_id:
                continue
            if c.technician_id and not (i.assigned_technician and i.assigned_technician.id == c.technician_id):
                continue
            if c.reporter_id and i.reporter.id != c.reporter_id:
                continue
            if c.sla_status and not (i.sla_tracker and i.sla_tracker.status is c.sla_status):
                continue
            if c.from_date and i.created_at.date() < c.from_date:
                continue
            if c.to_date and i.created_at.date() > c.to_date:
                continue
            if c.keyword and c.keyword.strip().lower() not in (i.title + " " + i.description).lower():
                continue
            found.append(i)
        return sorted(found, key=lambda i: i.created_at, reverse=True)

    def get_audit_trail(self, actor: User, incident_id: int):
        incident = self._load(actor, incident_id)
        return sorted((r for r in self._w.audits if r.incident_id == incident.id), key=lambda r: (r.timestamp, r.id))

    # ---- assignment --------------------------------------------------------------------------------
    def assign(self, actor: User, incident_id: int, technician_id: int) -> Incident:
        admin = _admin(actor)
        technician = self._w.users.get(technician_id)
        if technician is None:
            raise UserNotFoundError(f"User {technician_id} was not found")
        if not isinstance(technician, Technician):
            raise InvalidInputError("The chosen user is not a technician", "technician_id")

        def change(incident, now):
            count = self._active_count(technician.id)
            if incident.status is S.CLASSIFIED:
                incident.assign_to(admin, now, technician, count)
            else:
                incident.reassign(admin, now, technician, count)
        return self._act(admin, incident_id, "assign", change, IncidentEventType.ASSIGNED,
                         f"assigned to {technician.full_name}")

    def auto_assign(self, actor: User, incident_id: int) -> Incident:
        admin = _admin(actor)
        incident = self._load(admin, incident_id)
        pick = next((t for t in self._technicians() if t.available and t.active
                     and self._active_count(t.id) < t.max_workload), None)
        if pick is None:
            raise TechnicianUnavailableError("No technician is currently available for this incident")
        return self.assign(admin, incident.id, pick.id)

    def recommend_technicians(self, actor: User, incident_id: int) -> list[RankedTechnician]:
        admin = _admin(actor)
        incident = self._load(admin, incident_id)
        skill = incident.category.required_skill
        ranked = []
        for t in self._technicians():
            if not (t.available and t.active):
                continue
            has = skill in t.skills
            load = self._active_count(t.id)
            score = round(40 * has + 30 * (1 - load / t.max_workload) + 15 * min(t.experience_years, 10) / 10, 2)
            ranked.append(RankedTechnician(t, score, [f"has skill {skill}" if has else f"lacks skill {skill}",
                                                      f"{load} of {t.max_workload} slots used"]))
        return sorted(ranked, key=lambda r: -r.score)

    # ---- lifecycle ----------------------------------------------------------------------------------
    def acknowledge(self, actor, incident_id):
        return self._act(actor, incident_id, "acknowledge", lambda i, n: i.acknowledge(actor, n),
                         IncidentEventType.ACKNOWLEDGED, "the technician acknowledged your incident")

    def start_investigation(self, actor, incident_id):
        return self._act(actor, incident_id, "start investigation", lambda i, n: i.start_investigation(actor, n))

    def add_note(self, actor, incident_id, text):
        def add(incident, now):
            kind = NoteType.INFO_RESPONSE if actor.id == incident.reporter.id else NoteType.INVESTIGATION
            incident.add_note(actor, now, text, kind)
        return self._act(actor, incident_id, "add note", add)

    def request_info(self, actor, incident_id, question):
        return self._act(actor, incident_id, "request info", lambda i, n: i.request_info(actor, n, question),
                         IncidentEventType.INFO_REQUESTED, "more information is needed")

    def respond_to_info_request(self, actor, incident_id, answer):
        return self._act(actor, incident_id, "respond to info request", lambda i, n: i.respond_to_info(actor, n, answer))

    def resolve(self, actor, incident_id, summary, details):
        return self._act(actor, incident_id, "resolve", lambda i, n: i.resolve(actor, n, summary, details),
                         IncidentEventType.RESOLVED, "resolved, please verify the fix")

    def verify(self, actor, incident_id):
        return self._act(actor, incident_id, "verify", lambda i, n: i.verify(actor, n))

    def reject_resolution(self, actor, incident_id, reason):
        return self._act(actor, incident_id, "reject resolution", lambda i, n: i.reject_resolution(actor, n, reason))

    def close(self, actor, incident_id):
        return self._act(actor, incident_id, "close", lambda i, n: i.close(actor, n),
                         IncidentEventType.CLOSED, "closed")

    def submit_feedback(self, actor, incident_id, rating, comment):
        return self._act(actor, incident_id, "submit feedback", lambda i, n: i.submit_feedback(actor, n, rating, comment))

    def override_priority(self, actor: User, incident_id: int, priority: Priority, reason: str) -> Incident:
        admin = _admin(actor)
        if not isinstance(priority, Priority):
            raise InvalidInputError("Choose a valid priority", "priority")
        return self._act(admin, incident_id, "change priority",
                         lambda i, n: i.change_priority(admin, n, priority, reason, stub_tracker(priority, i.created_at)),
                         IncidentEventType.PRIORITY_CHANGED, f"priority is now {priority.name}")


class StubLookupService(LookupService):
    def __init__(self, world: StubWorld):
        self._w = world

    def list_active_services(self, actor: User) -> list[ITService]:
        _require(actor)
        return [s for s in self._w.services.values() if s.active]

    def list_active_categories(self, actor: User) -> list[Category]:
        _require(actor)
        return [c for c in self._w.categories.values() if c.active]

    def list_technicians(self, actor: User) -> list[Technician]:
        _admin(actor)
        return [u for u in self._w.users.values() if isinstance(u, Technician) and u.active]


class StubAdminService(AdminService):
    def __init__(self, world: StubWorld):
        self._w = world

    def _user(self, user_id: int) -> User:
        user = self._w.users.get(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")
        return user

    # ---- users ------------------------------------------------------------------------------------
    def list_users(self, actor):
        _admin(actor)
        return list(self._w.users.values())

    def create_user(self, actor, request: CreateUserRequest):
        _admin(actor)
        username = _text(request.username, "username")
        full = _text(request.full_name, "full_name")
        if len(request.password or "") < 8:
            raise InvalidInputError("Password must be at least 8 characters", "password")
        if any(u.username == username for u in self._w.users.values()):
            raise InvalidInputError("That username is already taken", "username")
        uid, email = self._w.next_user_id, request.email or f"{username}@stub.local"
        self._w.next_user_id += 1
        if request.role is Role.TECHNICIAN:
            user = Technician(username, full, email, "stub-hash", request.skills, request.experience_years,
                              True, request.max_workload, id=uid)
        elif request.role is Role.ADMINISTRATOR:
            if request.admin_level is None:
                raise InvalidInputError("An administrator needs an admin level", "admin_level")
            user = Administrator(username, full, email, "stub-hash", request.admin_level, id=uid)
        else:
            user = Employee(username, full, email, "stub-hash", request.department or "", id=uid)
        self._w.users[uid] = user
        return user

    def deactivate_user(self, actor, user_id):
        admin = _admin(actor)
        if admin.id == user_id:
            raise InvalidInputError("You cannot deactivate your own account", "user_id")
        user = self._user(user_id)
        user.deactivate()
        return user

    def activate_user(self, actor, user_id):
        _admin(actor)
        user = self._user(user_id)
        user.activate()
        return user

    def set_technician_availability(self, actor, user_id, available):
        _admin(actor)
        user = self._user(user_id)
        if not isinstance(user, Technician):
            raise InvalidInputError("Only technicians have an availability", "user_id")
        user.set_available(available)
        return user

    # ---- services, categories, policies ---------------------------------------------------------------
    def list_services(self, actor):
        _admin(actor)
        return list(self._w.services.values())

    def create_service(self, actor, request: ServiceRequest):
        _admin(actor)
        name = _text(request.name, "name")
        if any(s.name.lower() == name.lower() for s in self._w.services.values()):
            raise InvalidInputError(f"A service named '{name}' already exists", "name")
        sid = self._w.next_other_id
        self._w.next_other_id += 1
        service = ITService(name, request.description or "", request.business_criticality,
                            request.sla_policy_id, request.active, id=sid)
        self._w.services[sid] = service
        return service

    def update_service(self, actor, id, request: ServiceRequest):
        _admin(actor)
        if id not in self._w.services:
            raise ServiceNotFoundError(f"Service {id} was not found")
        service = ITService(_text(request.name, "name"), request.description or "", request.business_criticality,
                            request.sla_policy_id, request.active, id=id)
        self._w.services[id] = service
        return service

    def list_categories(self, actor):
        _admin(actor)
        return list(self._w.categories.values())

    def create_category(self, actor, request: CategoryRequest):
        _admin(actor)
        name = _text(request.name, "name")
        if any(c.name.lower() == name.lower() for c in self._w.categories.values()):
            raise InvalidInputError(f"A category named '{name}' already exists", "name")
        cid = self._w.next_other_id
        self._w.next_other_id += 1
        category = Category(name, request.description or "", _text(request.required_skill, "required_skill"),
                            request.active, id=cid)
        self._w.categories[cid] = category
        return category

    def update_category(self, actor, id, request: CategoryRequest):
        _admin(actor)
        if id not in self._w.categories:
            raise CategoryNotFoundError(f"Category {id} was not found")
        category = Category(_text(request.name, "name"), request.description or "",
                            _text(request.required_skill, "required_skill"), request.active, id=id)
        self._w.categories[id] = category
        return category

    def list_sla_policies(self, actor):
        _admin(actor)
        return list(self._w.policies.values())

    def save_sla_policy(self, actor, request: SlaPolicyRequest):
        _admin(actor)
        missing = [p.name for p in Priority if p not in (request.targets or {})]
        if missing:
            raise InvalidInputError(f"An SLA policy needs a target for every priority; missing {', '.join(missing)}", "targets")
        name = _text(request.name, "name")
        existing = next((p for p in self._w.policies.values() if p.name.lower() == name.lower()), None)
        pid = existing.id if existing else self._w.next_other_id
        if not existing:
            self._w.next_other_id += 1
        if request.is_default:
            for other in list(self._w.policies.values()):
                self._w.policies[other.id] = SlaPolicy(other.name, False, other.targets, id=other.id)
        policy = SlaPolicy(name, request.is_default, {p: SlaTarget(*request.targets[p]) for p in Priority}, id=pid)
        self._w.policies[pid] = policy
        return policy

    # ---- strategies --------------------------------------------------------------------------------------
    def list_assignment_strategies(self, actor):
        _admin(actor)
        return list(ASSIGNMENT_STRATEGIES)

    def get_assignment_strategy(self, actor):
        _admin(actor)
        return self._w.settings["assignment"]

    def set_assignment_strategy(self, actor, name):
        _admin(actor)
        if name not in ASSIGNMENT_STRATEGIES:
            raise InvalidInputError(f"Unknown strategy '{name}'", "name")
        self._w.settings["assignment"] = name

    def list_priority_strategies(self, actor):
        _admin(actor)
        return list(PRIORITY_STRATEGIES)

    def get_priority_strategy(self, actor):
        _admin(actor)
        return self._w.settings["priority"]

    def set_priority_strategy(self, actor, name):
        _admin(actor)
        if name not in PRIORITY_STRATEGIES:
            raise InvalidInputError(f"Unknown strategy '{name}'", "name")
        self._w.settings["priority"] = name

    # ---- demo clock and checks ------------------------------------------------------------------------------
    def is_time_simulated(self, actor) -> bool:
        _admin(actor)
        return True

    def get_current_time(self, actor) -> datetime:
        _admin(actor)
        return self._w.now()

    def advance_time(self, actor, minutes):
        _admin(actor)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
            raise InvalidInputError("Minutes must be a whole number of at least 1", "minutes")
        self._w.clock_offset += timedelta(minutes=minutes)
        return self._w.now()

    def reset_time(self, actor):
        _admin(actor)
        self._w.clock_offset = timedelta(0)
        return self._w.now()

    def run_sla_check_now(self, actor) -> int:
        """Stub: counts open incidents whose deadline has passed under the (possibly advanced) clock."""
        _admin(actor)
        now = self._w.now()
        return sum(1 for i in self._w.incidents.values() if i.status in _ACTIVE and i.sla_tracker
                   and i.sla_tracker.resolution_deadline < now and not i.sla_tracker.resolution_violated)

    def run_escalation_check_now(self, actor) -> int:
        """Stub: counts unacknowledged P1 incidents past their response deadline (nothing is escalated)."""
        _admin(actor)
        now = self._w.now()
        return sum(1 for i in self._w.incidents.values() if i.status is S.ASSIGNED and i.priority is Priority.P1
                   and i.sla_tracker and i.sla_tracker.response_deadline < now)


class StubReportService(ReportService):
    def __init__(self, world: StubWorld):
        self._w = world

    def overview(self, actor) -> OverviewReport:
        _admin(actor)
        incidents = list(self._w.incidents.values())
        unfinished = [i for i in incidents if i.status not in _FINISHED]
        return OverviewReport(
            total=len(incidents), open=len(unfinished),
            critical_open=sum(1 for i in unfinished if i.priority is Priority.P1), resolved=len(incidents) - len(unfinished),
            sla_violations=sum(1 for i in incidents if i.sla_tracker and i.sla_tracker.status.name == "VIOLATED"))

    def technician_workload(self, actor) -> list[WorkloadRow]:
        _admin(actor)
        rows = [WorkloadRow(t.id, t.full_name, sum(1 for i in self._w.incidents.values() if i.status in _ACTIVE
                                                  and i.assigned_technician and i.assigned_technician.id == t.id),
                            t.max_workload) for t in self._w.users.values() if isinstance(t, Technician)]
        return sorted(rows, key=lambda r: (-r.active_count, r.technician_name))

    def service_analysis(self, actor) -> list[CountRow]:
        _admin(actor)
        rows = [CountRow(s.name, sum(1 for i in self._w.incidents.values() if i.affected_service.id == s.id))
                for s in self._w.services.values()]
        return sorted(rows, key=lambda r: (-r.count, r.label))

    def category_analysis(self, actor) -> list[CountRow]:
        _admin(actor)
        rows = [CountRow(c.name, sum(1 for i in self._w.incidents.values() if i.category.id == c.id))
                for c in self._w.categories.values()]
        return sorted(rows, key=lambda r: (-r.count, r.label))

    def sla_violations(self, actor) -> list[SlaViolationRow]:
        _admin(actor)
        return [SlaViolationRow(i.ticket_number, i.title, i.priority,
                                i.assigned_technician.full_name if i.assigned_technician else None,
                                SlaEventType.RESOLUTION_VIOLATED, i.sla_tracker.resolution_deadline)
                for i in self._w.incidents.values() if i.sla_tracker and i.sla_tracker.status.name == "VIOLATED"]

    def audit_log(self, actor, audit_filter: AuditFilter):
        _admin(actor)
        f = audit_filter
        rows = [r for r in self._w.audits
                if (f.incident_id is None or r.incident_id == f.incident_id)
                and (f.actor_id is None or r.actor_id == f.actor_id)
                and (f.action is None or r.action == f.action)
                and (f.from_date is None or r.timestamp.date() >= f.from_date)
                and (f.to_date is None or r.timestamp.date() <= f.to_date)]
        return sorted(rows, key=lambda r: (r.timestamp, r.id), reverse=True)

    def correlation_groups(self, actor):
        """Stub: correlation needs the domain's detector, which the web layer may not import."""
        _admin(actor)
        return []


class StubNotificationService(NotificationService):
    def __init__(self, world: StubWorld):
        self._w = world

    def _mine(self, user: User):
        return [n for n in self._w.notifications if n.recipient_id == user.id]

    def list_for_user(self, actor, limit):
        user = _require(actor)
        return sorted(self._mine(user), key=lambda n: (n.created_at, n.id), reverse=True)[:max(1, min(int(limit), 200))]

    def unread_count(self, actor) -> int:
        return sum(1 for n in self._mine(_require(actor)) if not n.is_read)

    def mark_read(self, actor, notification_id) -> None:
        user = _require(actor)
        for index, n in enumerate(self._w.notifications):
            if n.id == notification_id and n.recipient_id == user.id:
                self._w.notifications[index] = replace(n, is_read=True)
                return
        raise UnauthorizedOperationError("You can only mark your own notifications as read")

    def mark_all_read(self, actor) -> None:
        user = _require(actor)
        for index, n in enumerate(self._w.notifications):
            if n.recipient_id == user.id:
                self._w.notifications[index] = replace(n, is_read=True)

