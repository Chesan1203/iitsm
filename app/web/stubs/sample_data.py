"""Hard-coded sample data for stub mode (ITSM_MODE=stub): no database, no real services.

Built only from the domain's own entity classes, so pages see exactly the object shapes the real
services return. Every user has the password `Password@123`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.enums import (
    AdminLevel, ChannelType, IncidentEventType, IncidentStatus as S, Level, NoteType, Priority,
    SlaStatus,
)
from app.domain.models.audit import AuditRecord
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Administrator, Employee, Technician, User

PASSWORD = "Password@123"
ERROR_INCIDENT_ID = 999            # every action on this incident raises InvalidStateTransitionError

# Stub-only copies of the business rules (the real ones live in the domain's BusinessRules and
# strategies, which the web layer is not allowed to import).
SLA_MINUTES = {Priority.P1: (5, 30), Priority.P2: (15, 120), Priority.P3: (60, 480), Priority.P4: (240, 1440)}


def stub_priority(impact: Level, urgency: Level, criticality: Level, users: int) -> tuple[Priority, int]:
    """score = impact x urgency x criticality; 18+ P1, 9+ P2, 4+ P3, else P4; 50+ users raise one level."""
    score = impact.value * urgency.value * criticality.value
    priority = Priority.P1 if score >= 18 else Priority.P2 if score >= 9 else Priority.P3 if score >= 4 else Priority.P4
    if users >= 50 and priority is not Priority.P1:
        priority = Priority(priority.value - 1)
    return priority, score


def stub_tracker(priority: Priority, created: datetime, status: SlaStatus = SlaStatus.ON_TRACK) -> SlaTracker:
    response, resolution = SLA_MINUTES[priority]
    return SlaTracker(created + timedelta(minutes=response), created + timedelta(minutes=resolution), status=status)


@dataclass
class StubWorld:
    """Everything the stub services read and change. One per application start."""
    users: dict[int, User] = field(default_factory=dict)
    services: dict[int, ITService] = field(default_factory=dict)
    categories: dict[int, Category] = field(default_factory=dict)
    policies: dict[int, SlaPolicy] = field(default_factory=dict)
    incidents: dict[int, Incident] = field(default_factory=dict)
    audits: list[AuditRecord] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)
    settings: dict[str, str] = field(default_factory=lambda: {
        "priority": "weighted_score", "assignment": "skill_based"})
    clock_offset: timedelta = timedelta(0)
    next_user_id: int = 10
    next_incident_id: int = 10
    next_other_id: int = 10

    def now(self) -> datetime:
        return datetime.now().replace(microsecond=0) + self.clock_offset

    def user(self, username: str) -> User:
        return next(u for u in self.users.values() if u.username == username)

    def log(self, incident: Incident, actor: User, action: str, previous, new, description: str, at=None) -> None:
        self.audits.append(AuditRecord(
            id=len(self.audits) + 1, incident_id=incident.id, ticket_number=incident.ticket_number,
            timestamp=at or self.now(), actor_id=actor.id, actor_name=actor.full_name, action=action,
            previous_status=previous, new_status=new, description=description))

    def notify(self, recipient: User, incident: Incident, kind: IncidentEventType, message: str) -> None:
        self.notifications.append(Notification(
            id=len(self.notifications) + 1, recipient_id=recipient.id, incident_id=incident.id, event_type=kind,
            channel=ChannelType.IN_APP, message=message, created_at=self.now()))


def build_world() -> StubWorld:
    world = StubWorld()
    now = world.now()

    def add(user: User) -> User:
        world.users[user.id] = user
        return user

    for i, (name, full, dept) in enumerate([("emp1", "Asha Verma", "Finance"), ("emp2", "Rohan Gupta", "Marketing"),
                                            ("emp3", "Divya Nambiar", "Human Resources")], start=1):
        add(Employee(name, full, f"{name}@stub.local", "stub-hash", dept, id=i))
    for i, (name, full, skills, years, free) in enumerate([
            ("tech1", "Ravi Kumar", {"Database", "Application"}, 8, True),
            ("tech2", "Priya Menon", {"Network", "Security"}, 6, True),
            ("tech3", "Arjun Das", {"Application"}, 5, False)], start=4):
        add(Technician(name, full, f"{name}@stub.local", "stub-hash", skills, years, free, 5, id=i))
    for i, (name, full, level) in enumerate([("admin1", "Meera Nair", AdminLevel.TEAM_LEAD),
                                             ("admin2", "Karthik Iyer", AdminLevel.SYSTEM_ADMIN),
                                             ("admin3", "Sunita Rao", AdminLevel.IT_MANAGER)], start=7):
        add(Administrator(name, full, f"{name}@stub.local", "stub-hash", level, id=i))

    for i, (name, desc, crit) in enumerate([("Payment", "Customer payments", Level.HIGH), ("Network", "LAN and WiFi", Level.HIGH),
                                            ("Email", "Corporate email", Level.LOW), ("Database", "Core databases", Level.HIGH)], start=1):
        world.services[i] = ITService(name, desc, crit, id=i)
    for i, name in enumerate(["Application", "Network", "Database"], start=1):
        world.categories[i] = Category(name, f"{name} issues", name, id=i)
    world.policies[1] = SlaPolicy("Default", True, {p: SlaTarget(r, s) for p, (r, s) in SLA_MINUTES.items()}, id=1)

    # id, title, description, reporter, service, category, impact, urgency, users, status, technician, age (minutes)
    specs = [
        (1, "Payment application unavailable", "Users cannot complete transactions.", "emp1", 1, 1, Level.HIGH, Level.HIGH, 180, S.IN_PROGRESS, "tech1", 40),
        (2, "Payment transaction failing", "Card payments fail at confirmation.", "emp2", 1, 1, Level.HIGH, Level.HIGH, 120, S.ASSIGNED, "tech1", 3),
        (3, "Cannot reach internal websites", "Internal sites time out on floor 2.", "emp1", 2, 2, Level.MEDIUM, Level.MEDIUM, 30, S.ACKNOWLEDGED, "tech2", 25),
        (4, "VPN drops every ten minutes", "Remote staff are disconnected.", "emp3", 2, 2, Level.MEDIUM, Level.HIGH, 40, S.RESOLVED, "tech2", 90),
        (5, "Email signature tool broken", "The generator shows a blank page.", "emp2", 3, 1, Level.LOW, Level.LOW, 2, S.VERIFIED, "tech1", 300),
        (6, "Database replication lag alerts", "The replica is behind the primary.", "emp1", 4, 3, Level.MEDIUM, Level.MEDIUM, 80, S.CLOSED, "tech1", 1500),
        (7, "Wifi dead zone in building B", "No signal in the east wing.", "emp3", 2, 2, Level.LOW, Level.MEDIUM, 30, S.CLASSIFIED, None, 6),
        (ERROR_INCIDENT_ID, "Stub incident for error testing", "Every action on this incident is refused.", "emp1", 3, 1, Level.LOW, Level.LOW, 1, S.ASSIGNED, "tech1", 120),
    ]
    order = list(S)
    for iid, title, desc, reporter, service, category, impact, urgency, users, status, tech, age in specs:
        created = now - timedelta(minutes=age)
        reached = lambda s, status=status: order.index(status) >= order.index(s)       # noqa: E731
        priority, score = stub_priority(impact, urgency, world.services[service].business_criticality, users)
        technician = world.user(tech) if tech else None
        resolver = technician
        elapsed_ack = created + timedelta(minutes=4)
        notes = []
        if reached(S.IN_PROGRESS):
            notes = [InvestigationNote(id=1, author=technician, note_type=NoteType.INVESTIGATION,
                                       text="Reproduced the problem and checking logs.", created_at=created + timedelta(minutes=6)),
                     InvestigationNote(id=2, author=technician, note_type=NoteType.INFO_REQUEST,
                                       text="Which browser are you using?", created_at=created + timedelta(minutes=8))] if iid == 1 else [
                InvestigationNote(id=1, author=technician, note_type=NoteType.INVESTIGATION,
                                  text="Looking into it.", created_at=created + timedelta(minutes=6))]
        tracker_status = SlaStatus.VIOLATED if iid == 1 else SlaStatus.MET if status in (S.RESOLVED, S.VERIFIED, S.CLOSED) else SlaStatus.ON_TRACK
        snapshot = IncidentSnapshot(
            id=iid, ticket_number=f"INC-{1000 + iid}", title=title, description=desc,
            reporter=world.user(reporter), category=world.categories[category], affected_service=world.services[service],
            impact=impact, urgency=urgency, affected_users=users, priority=priority, priority_score=score,
            status=status, created_at=created, assigned_technician=technician,
            assigned_at=created + timedelta(minutes=2) if technician else None,
            acknowledged_at=elapsed_ack if reached(S.ACKNOWLEDGED) else None,
            resolved_at=created + timedelta(minutes=20) if reached(S.RESOLVED) else None,
            verified_at=created + timedelta(minutes=25) if reached(S.VERIFIED) else None,
            closed_at=created + timedelta(minutes=30) if reached(S.CLOSED) else None,
            possible_duplicate_of="INC-1001" if iid == 2 else None, notes=tuple(notes),
            resolution=Resolution("Applied the fix", "Restarted the affected service.", resolver, created + timedelta(minutes=20)) if reached(S.RESOLVED) else None,
            feedback=Feedback(5, "Quick fix, thanks.", created + timedelta(minutes=28)) if reached(S.CLOSED) else None,
            sla_tracker=stub_tracker(priority, created, tracker_status))
        incident = Incident.restore(snapshot)
        world.incidents[iid] = incident

        who = world.user(reporter)
        world.log(incident, who, "CREATED", None, S.NEW, f"Incident created by {who.full_name}", created)
        world.log(incident, User.system(), "CLASSIFIED", S.NEW, S.CLASSIFIED, f"Priority {priority.name} (score {score})", created + timedelta(minutes=1))
        if technician:
            world.log(incident, User.system(), "ASSIGNED", S.CLASSIFIED, S.ASSIGNED, f"Assigned to {technician.full_name}", created + timedelta(minutes=2))
        if reached(S.ACKNOWLEDGED):
            world.log(incident, technician, "ACKNOWLEDGED", S.ASSIGNED, S.ACKNOWLEDGED, "Acknowledged", elapsed_ack)
        if reached(S.IN_PROGRESS):
            world.log(incident, technician, "INVESTIGATION_STARTED", S.ACKNOWLEDGED, S.IN_PROGRESS, "Investigation started", created + timedelta(minutes=5))
        if reached(S.RESOLVED):
            world.log(incident, technician, "RESOLVED", S.IN_PROGRESS, S.RESOLVED, "Applied the fix", created + timedelta(minutes=20))
        if reached(S.VERIFIED):
            world.log(incident, who, "VERIFIED", S.RESOLVED, S.VERIFIED, "Resolution verified", created + timedelta(minutes=25))
        if reached(S.CLOSED):
            world.log(incident, who, "CLOSED", S.VERIFIED, S.CLOSED, "Incident closed", created + timedelta(minutes=30))

    world.notify(world.user("emp1"), world.incidents[1], IncidentEventType.ACKNOWLEDGED, "tech1 acknowledged INC-1001")
    world.notify(world.user("emp1"), world.incidents[3], IncidentEventType.ASSIGNED, "INC-1003 was assigned to Priya Menon")
    world.notify(world.user("emp3"), world.incidents[4], IncidentEventType.RESOLVED, "INC-1004 has been resolved. Please verify the fix.")
    world.notify(world.user("tech1"), world.incidents[2], IncidentEventType.ASSIGNED, "INC-1002 was assigned to you")
    world.notify(world.user("admin1"), world.incidents[2], IncidentEventType.DUPLICATE_FLAGGED, "INC-1002 may be a duplicate of INC-1001")
    world.notify(world.user("admin1"), world.incidents[1], IncidentEventType.SLA_VIOLATED, "SLA violated: INC-1001 missed a deadline")
    return world
