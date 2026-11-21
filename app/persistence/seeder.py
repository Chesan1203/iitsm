"""Demo data for the I-ITSM app.

`DemoDataSeeder.seed_if_empty()` fills an empty database with users, reference data and about
45 incidents spread over the last two weeks. Everything is dated relative to the time
provider's "now", so SLA states look right whenever the app starts.

Planted for the demo (see docs/demo_data.md):
  * three Payment incidents that the duplicate detector flags as related
  * three Network incidents within the last hour (a probable service-level problem)
  * several incidents that are already SLA-violated, and one in its warning zone
  * one P1 on Database assigned a minute ago and not yet acknowledged: advance the demo clock
    a few minutes and the escalation job escalates it
  * two Cloud incidents left CLASSIFIED because the only Cloud technician is unavailable

Run on its own with:  python -m app.persistence.seeder

The domain engines (priority strategy, SLA calculator) compute priorities and SLA status, so
the seeded data always agrees with what the live system would have produced.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import bcrypt

from app.domain.business_rules import BusinessRules
from app.domain.enums import (
    AdminLevel, ChannelType, IncidentEventType, IncidentStatus as S, Level, NoteType, Priority,
    SlaEventType,
)
from app.domain.models.audit import AuditRecord
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent, SlaPolicy, SlaTarget
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Administrator, Employee, Technician, User
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.strategies.priority import PriorityInput, WeightedScorePriorityStrategy
from app.domain.time_provider import TimeProvider
from app.ports.repositories import (
    AuditRepository, CategoryRepository, IncidentRepository, NotificationRepository,
    ServiceRepository, SlaEventRepository, SlaPolicyRepository, UserRepository,
)

logger = logging.getLogger(__name__)

H, M, L = Level.HIGH, Level.MEDIUM, Level.LOW

# ---- reference data ------------------------------------------------------------------------

ADMINS = [("admin1", "Meera Nair", AdminLevel.TEAM_LEAD),
          ("admin2", "Karthik Iyer", AdminLevel.SYSTEM_ADMIN),
          ("admin3", "Sunita Rao", AdminLevel.IT_MANAGER),
          ("admin4", "Vikram Shah", AdminLevel.SYSTEM_ADMIN)]

# username, name, skills, experience years, available. tech6 is on leave and is the only
# technician with the Cloud skill, which is why the two Cloud incidents stay unassigned.
TECHNICIANS = [("tech1", "Ravi Kumar", {"Database", "Storage", "Application"}, 8, True),
               ("tech2", "Priya Menon", {"Network", "Security"}, 6, True),
               ("tech3", "Arjun Das", {"Application", "Software"}, 5, True),
               ("tech4", "Neha Kapoor", {"Authentication", "Security"}, 7, True),
               ("tech5", "Sanjay Patil", {"Hardware", "Storage"}, 3, True),
               ("tech6", "Lakshmi Rao", {"Cloud", "Network", "Database"}, 10, False)]

EMPLOYEES = [("emp1", "Asha Verma", "Finance"), ("emp2", "Rohan Gupta", "Marketing"),
             ("emp3", "Divya Nambiar", "Human Resources"), ("emp4", "Imran Sheikh", "Sales"),
             ("emp5", "Kavya Reddy", "Finance"), ("emp6", "Manish Joshi", "Operations"),
             ("emp7", "Pooja Bhatt", "Legal"), ("emp8", "Suresh Pillai", "Operations"),
             ("emp9", "Tanvi Desai", "Marketing"), ("emp10", "Yash Malhotra", "Sales")]

CATEGORIES = ["Hardware", "Software", "Network", "Database", "Cloud", "Security",
              "Authentication", "Application", "Storage"]          # required_skill = the name

SERVICES = [("Payment", "Customer payment processing", H), ("Database", "Core databases", H),
            ("Network", "Corporate LAN, WiFi and firewall", H),
            ("Authentication", "Single sign-on and directory", H),
            ("Cloud Storage", "File storage and sync", M), ("ERP", "Finance and HR system", M),
            ("Email", "Corporate email", L), ("VPN", "Remote access", M)]

STRICT_SLA = {Priority.P1: (3, 20), Priority.P2: (10, 90), Priority.P3: (30, 360),
              Priority.P4: (120, 720)}                      # attached to the Payment service

_INVESTIGATION_NOTES = ["Reviewed the logs and reproduced the problem.",
                        "No recent changes found in the last 24 hours; checking dependencies.",
                        "Confirmed the fault with the vendor and testing a workaround."]
_RESOLUTIONS = {
    "Network": ("Replaced faulty configuration", "Rolled back the last network change and verified."),
    "Database": ("Tuned database settings", "Increased limits and restarted the affected service."),
    "Authentication": ("Reset the identity cache", "Cleared stale sessions and re-synced the directory."),
    "Application": ("Applied application hotfix", "Deployed the patched build and confirmed with users."),
    "Storage": ("Freed and extended storage", "Archived old data and raised the quota."),
    "Security": ("Blocked the threat and informed users", "Added a mail rule and a firewall block."),
    "Cloud": ("Reconnected the cloud service", "Renewed the integration token."),
    "Hardware": ("Replaced the failed part", "Swapped the part and tested the link."),
    "Software": ("Reinstalled the software", "Installed the latest version and checked the settings."),
}
_RATINGS = [5, 4, 5, 3, 4, 5]


@dataclass(frozen=True)
class _Spec:
    """One demo incident. a, b and idle mean different things per status, see _timeline()."""
    title: str
    description: str
    service: str
    category: str
    impact: Level
    urgency: Level
    users: int
    status: S
    a: float = 0.4
    b: float = 0.5
    idle: float = 0.0               # minutes
    key: str | None = None
    duplicate_of: str | None = None


def _closed(*row):
    return _Spec(*row[:7], S.CLOSED, row[7], row[8], row[9] * 1440)


# title, description, service, category, impact, urgency, users, ack fraction, resolve fraction, days since
SPECS: list[_Spec] = [
    _closed("Email delivery delayed for finance team", "Messages to external recipients arrive 30 to 40 minutes late.", "Email", "Application", M, M, 25, .4, .5, 12),
    _closed("VPN disconnects every 10 minutes", "Remote staff are dropped from the VPN roughly every ten minutes.", "VPN", "Network", M, H, 40, .3, .6, 11),
    _closed("Cannot log in after password reset", "The reset password is rejected with an invalid credentials error.", "Authentication", "Authentication", M, M, 3, .5, .4, 10),
    _closed("Cloud storage quota exceeded for marketing", "Marketing cannot upload new campaign files.", "Cloud Storage", "Storage", L, M, 12, .6, .5, 9),
    _closed("ERP month-end report timing out", "Finance cannot run the month-end ledger report.", "ERP", "Application", M, M, 15, .5, .7, 9),
    _closed("Database replication lag alerts", "The replica is more than 10 minutes behind the primary.", "Database", "Database", M, M, 80, .4, 1.3, 8),
    _closed("Wifi dead zone in building B", "No signal in the east wing of building B.", "Network", "Network", L, M, 30, .3, .4, 8),
    _closed("Phishing email reported by HR", "HR received a suspicious message asking for payroll login.", "Email", "Security", M, M, 5, .2, .3, 7),
    _closed("Payment gateway intermittent timeouts", "Some card payments time out after 30 seconds.", "Payment", "Application", H, M, 200, 1.5, 1.1, 7),
    _closed("Laptop cannot connect to VPN", "A new laptop shows a certificate error in the VPN client.", "VPN", "Network", L, L, 1, .3, .3, 6),
    _closed("SSO login loop on intranet", "The intranet keeps redirecting back to the sign-in page.", "Authentication", "Authentication", M, M, 60, .5, .5, 6),
    _closed("Shared drive permission denied", "The project folder returns access denied for the whole team.", "Cloud Storage", "Storage", L, L, 4, .4, .5, 5),
    _closed("Slow queries on reporting database", "Dashboards take over a minute to load.", "Database", "Database", M, M, 20, 1.4, .6, 5),
    _closed("Firewall rule blocks partner API", "Partner integration calls are rejected at the firewall.", "Network", "Security", L, H, 10, .3, .4, 4),
    _closed("Email signature tool broken", "The signature generator shows a blank page.", "Email", "Software", L, L, 2, .3, .3, 4),
    _closed("ERP login fails for new joiners", "New accounts cannot sign in to ERP on their first day.", "ERP", "Authentication", M, M, 6, .4, .5, 3),
    _closed("Backup job failed overnight", "The nightly database backup finished with errors.", "Database", "Storage", M, M, 1, .4, 1.2, 3),
    _closed("Cloud file sync stuck", "The desktop sync client shows syncing for hours.", "Cloud Storage", "Cloud", M, L, 10, .3, .4, 3),
    _closed("Network switch port dead in server room", "Rack 4 port 12 shows no link light.", "Network", "Hardware", M, M, 15, .4, .5, 2),
    _closed("VPN client update fails", "The update installer exits with error 1603.", "VPN", "Software", L, M, 18, .3, .4, 2),
    _closed("Payment receipts not emailed", "Customers do not receive receipts after paying.", "Payment", "Application", M, L, 40, .5, .5, 2),

    _Spec("Intranet portal returns 500 error", "The staff portal shows an internal server error after login.", "ERP", "Application", M, M, 30, S.VERIFIED, .4, .5, 360),
    _Spec("VPN token expired for remote staff", "Hardware tokens stopped working after the weekend.", "VPN", "Authentication", M, H, 22, S.VERIFIED, .3, .4, 1200),
    _Spec("Email attachments over 5 MB bounce", "Large attachments are rejected by the mail gateway.", "Email", "Application", L, M, 14, S.VERIFIED, .3, .5, 1800),

    _Spec("Database connection pool exhausted", "Application servers report no free database connections.", "Database", "Database", H, H, 150, S.RESOLVED, .4, .6, 90),
    _Spec("Cloud storage sharing links expired", "Share links stop working after a day.", "Cloud Storage", "Cloud", L, M, 9, S.RESOLVED, .3, .4, 180),
    _Spec("Cannot join video calls over VPN", "Video calls freeze while the VPN is connected.", "VPN", "Network", M, M, 35, S.RESOLVED, .4, .5, 120),
    _Spec("Authentication service slow at 9am", "Sign-in takes 20 seconds during the morning peak.", "Authentication", "Authentication", M, H, 70, S.RESOLVED, .3, .7, 45),

    _Spec("Payment application unavailable", "Users are unable to complete transactions in the payment application.", "Payment", "Application", H, H, 180, S.IN_PROGRESS, .4, 4.5, key="pay1"),
    _Spec("Network outage in building A", "No network access on any floor of building A.", "Network", "Network", M, M, 45, S.IN_PROGRESS, .3, .33),
    _Spec("Primary mail server queue growing", "The outbound mail queue has more than 4000 messages.", "Email", "Application", H, M, 300, S.IN_PROGRESS, .3, .85),
    _Spec("ERP invoice posting errors", "Posting invoices fails with a ledger lock message.", "ERP", "Application", M, M, 18, S.IN_PROGRESS, .4, .4),
    _Spec("Database disk usage at 92 percent", "The data volume is almost full on the primary server.", "Database", "Storage", M, H, 10, S.IN_PROGRESS, .4, .5),
    _Spec("Users locked out of SSO portal", "Many staff see account locked after one failed attempt.", "Authentication", "Authentication", H, M, 55, S.IN_PROGRESS, .4, .7),
    _Spec("Cloud backup throttled", "Backups to cloud storage run at a tenth of normal speed.", "Cloud Storage", "Storage", L, L, 3, S.IN_PROGRESS, .3, .3),
    _Spec("VPN gateway high CPU", "The gateway CPU sits above 90 percent at peak hours.", "VPN", "Network", M, M, 20, S.IN_PROGRESS, .3, .6),

    _Spec("Payment transaction failing", "Card transactions fail at the final confirmation step.", "Payment", "Application", H, H, 120, S.ACKNOWLEDGED, .5, idle=52, key="pay2", duplicate_of="pay1"),
    _Spec("Cannot reach internal websites from floor 2", "Internal sites time out for users on the second floor.", "Network", "Network", M, M, 30, S.ACKNOWLEDGED, .3, idle=20.5),
    _Spec("Intranet search not returning results", "Search always shows no results.", "ERP", "Application", L, M, 12, S.ACKNOWLEDGED, .4, idle=35),

    _Spec("Unable to make payment", "Customers report they cannot make a payment.", "Payment", "Application", M, M, 15, S.ASSIGNED, 2.0, key="pay3", duplicate_of="pay1"),
    _Spec("Wifi keeps dropping on third floor", "The wireless connection drops every few minutes.", "Network", "Network", M, M, 25, S.ASSIGNED, .87),
    _Spec("New hire needs ERP access", "Access request for ERP for a new finance analyst.", "ERP", "Authentication", L, L, 1, S.ASSIGNED, .3),

    _Spec("Cloud object storage replication delayed", "Replication to the secondary region is hours behind.", "Cloud Storage", "Cloud", M, M, 20, S.CLASSIFIED, idle=6),
    _Spec("Cloud VM snapshot job missing", "Scheduled snapshots did not run last night.", "Cloud Storage", "Cloud", L, M, 4, S.CLASSIFIED, idle=9),
]

# The escalation demo: created 2 minutes ago, assigned 1 minute ago, never acknowledged.
ESCALATION_SPEC = _Spec("Primary database cluster unreachable", "Applications cannot connect to the primary database cluster.",
                        "Database", "Database", H, H, 300, S.ASSIGNED)


@dataclass
class _Built:
    spec: _Spec
    snapshot: IncidentSnapshot
    events: list[tuple[SlaEventType, datetime]]
    inv_at: datetime | None


def _td(minutes: float) -> timedelta:
    return timedelta(seconds=round(minutes * 60))


class DemoDataSeeder:
    def __init__(self, users: UserRepository, categories: CategoryRepository,
                 services: ServiceRepository, policies: SlaPolicyRepository,
                 incidents: IncidentRepository, audits: AuditRepository,
                 notifications: NotificationRepository, sla_events: SlaEventRepository,
                 time_provider: TimeProvider, password_hash: str | None = None):
        self._users, self._categories, self._services = users, categories, services
        self._policies, self._incidents, self._audits = policies, incidents, audits
        self._notifications, self._sla_events, self._time = notifications, sla_events, time_provider
        self._password_hash = password_hash       # tests may pass a cheap hash; None = real bcrypt
        self._priority = WeightedScorePriorityStrategy()
        self._sla = SlaCalculator()

    # ---- public ---------------------------------------------------------------------------
    def seed_if_empty(self) -> bool:
        """Seed an empty database and return True; do nothing and return False if there are
        already users. (Seeding is not one transaction: if it is ever interrupted, delete the
        database file and run it again.)"""
        if self._users.find_all():
            return False
        now = self._time.now().replace(microsecond=0)
        self._create_people()
        self._create_reference_data()
        built = [self._build(spec, i, now) for i, spec in enumerate(SPECS)]
        built.append(self._build_escalation_case(len(SPECS), now))
        self._save_incidents(sorted(built, key=lambda b: b.snapshot.created_at), now)
        logger.info("Seeded demo data: %d incidents", len(built))
        return True

    # ---- people and reference data ----------------------------------------------------------
    def _create_people(self) -> None:
        pw = self._password_hash or bcrypt.hashpw(
            BusinessRules.DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()  # hashed once, reused
        for username, name, level in ADMINS:
            self._users.save(Administrator(username, name, f"{username}@iitsm.local", pw, level))
        self._technicians: list[Technician] = [
            self._users.save(Technician(u, n, f"{u}@iitsm.local", pw, skills, exp, avail))
            for u, n, skills, exp, avail in TECHNICIANS]
        self._employees: list[Employee] = [
            self._users.save(Employee(u, n, f"{u}@iitsm.local", pw, dept)) for u, n, dept in EMPLOYEES]
        self._admins = [u for u in self._users.find_all() if isinstance(u, Administrator)]
        self._open_load = {t.username: 0 for t in self._technicians}
        self._total_load = {t.username: 0 for t in self._technicians}

    def _create_reference_data(self) -> None:
        self._default_policy = self._policies.save(SlaPolicy("Default", True, {
            p: SlaTarget(*minutes) for p, minutes in BusinessRules.DEFAULT_SLA_TARGET_MINUTES.items()}))
        strict = self._policies.save(SlaPolicy("Critical Services", False, {
            p: SlaTarget(*minutes) for p, minutes in STRICT_SLA.items()}))
        self._category = {n: self._categories.save(Category(n, f"{n} related issues", n))
                          for n in CATEGORIES}
        self._service = {}
        for name, description, criticality in SERVICES:
            policy_id = strict.id if name == "Payment" else None
            self._service[name] = self._services.save(
                ITService(name, description, criticality, policy_id))
        self._strict_policy = strict

    # ---- building incidents -----------------------------------------------------------------
    def _policy_for(self, service: ITService) -> SlaPolicy:
        return self._strict_policy if service.sla_policy_id == self._strict_policy.id else self._default_policy

    def _pick_technician(self, skill: str, is_open: bool) -> Technician:
        """Open incidents go to an available technician with spare capacity (least busy first);
        historical ones may also go to technicians who are now on leave."""
        pool = [t for t in self._technicians if skill in t.skills
                and (not is_open or (t.available and self._open_load[t.username] < t.max_workload))]
        if not pool:
            raise RuntimeError(f"No technician can take a {skill} incident")
        chosen = min(pool, key=lambda t: (self._open_load[t.username] if is_open
                                          else self._total_load[t.username], t.username))
        self._total_load[chosen.username] += 1
        if is_open:
            self._open_load[chosen.username] += 1
        return chosen

    def _timeline(self, spec: _Spec, resp: int, res: int) -> dict:
        """Minutes after creation for every lifecycle step the status implies, plus the age."""
        t = {"classified": 1.0, "assigned": 2.0}
        status = spec.status
        t["ack"] = max(3.0, spec.a * resp)
        t["inv"] = t["ack"] + 1.0
        t["resolved"] = max(t["ack"] + 6.0, spec.b * res)
        t["verified"] = t["resolved"] + 10.0
        t["closed"] = t["verified"] + 5.0
        if status is S.CLOSED:
            t["age"] = t["closed"] + spec.idle
        elif status is S.VERIFIED:
            t["age"] = t["verified"] + spec.idle
        elif status is S.RESOLVED:
            t["age"] = t["resolved"] + spec.idle
        elif status is S.IN_PROGRESS:
            t["age"] = max(spec.b * res, t["inv"] + 5.0)
        elif status is S.ACKNOWLEDGED:
            t["age"] = t["ack"] + spec.idle
        elif status is S.ASSIGNED:
            t["age"] = max(3.0, spec.a * resp)
        else:
            t["age"] = max(2.0, spec.idle)
        return t

    def _build(self, spec: _Spec, index: int, now: datetime) -> _Built:
        service, category = self._service[spec.service], self._category[spec.category]
        result = self._priority.calculate(
            PriorityInput(spec.impact, spec.urgency, service.business_criticality, spec.users))
        policy = self._policy_for(service)
        target = policy.target_for(result.priority)
        t = self._timeline(spec, target.response_minutes, target.resolution_minutes)
        created = now - _td(t["age"])
        reporter = self._employees[index % len(self._employees)]
        order = list(S)
        reached = lambda status: order.index(spec.status) >= order.index(status)  # noqa: E731
        is_open = spec.status in (S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS)
        tech = self._pick_technician(category.required_skill, is_open) if reached(S.ASSIGNED) else None
        stamp = lambda key: created + _td(t[key])  # noqa: E731

        notes, resolution, feedback = [], None, None
        if reached(S.IN_PROGRESS):
            notes.append(InvestigationNote(author=tech, note_type=NoteType.INVESTIGATION,
                                           text=_INVESTIGATION_NOTES[index % 3], created_at=stamp("inv") + _td(1)))
            if index % 4 == 0:
                notes.append(InvestigationNote(author=tech, note_type=NoteType.INFO_REQUEST,
                                               text="Can you tell me exactly when this started?",
                                               created_at=stamp("inv") + _td(1.5)))
                notes.append(InvestigationNote(author=reporter, note_type=NoteType.INFO_RESPONSE,
                                               text="It started shortly after 9am today.",
                                               created_at=stamp("inv") + _td(2)))
        if reached(S.RESOLVED):
            summary, details = _RESOLUTIONS[category.name]
            resolution = Resolution(summary, details, tech, stamp("resolved"))
        if reached(S.VERIFIED) and index % 2 == 0:
            feedback = Feedback(_RATINGS[index % len(_RATINGS)], "Thanks, resolved quickly.",
                                stamp("verified") + _td(3))

        snapshot = IncidentSnapshot(
            title=spec.title, description=spec.description, reporter=reporter, category=category,
            affected_service=service, impact=spec.impact, urgency=spec.urgency,
            affected_users=spec.users, priority=result.priority, priority_score=result.score,
            status=spec.status, created_at=created,
            assigned_technician=tech, assigned_at=stamp("assigned") if tech else None,
            acknowledged_at=stamp("ack") if reached(S.ACKNOWLEDGED) else None,
            resolved_at=stamp("resolved") if reached(S.RESOLVED) else None,
            verified_at=stamp("verified") if reached(S.VERIFIED) else None,
            closed_at=stamp("closed") if reached(S.CLOSED) else None,
            notes=tuple(notes), resolution=resolution, feedback=feedback,
            sla_tracker=self._sla.create_tracker(result.priority, policy, created)
            if reached(S.CLASSIFIED) else None)
        snapshot, events = self._with_sla_state(snapshot, now)
        return _Built(spec, snapshot, events, stamp("inv") if reached(S.IN_PROGRESS) else None)

    def _build_escalation_case(self, index: int, now: datetime) -> _Built:
        spec = ESCALATION_SPEC
        service, category = self._service[spec.service], self._category[spec.category]
        result = self._priority.calculate(
            PriorityInput(spec.impact, spec.urgency, service.business_criticality, spec.users))
        created = now - _td(2)
        tech = self._pick_technician(category.required_skill, True)
        snapshot = IncidentSnapshot(
            title=spec.title, description=spec.description,
            reporter=self._employees[index % len(self._employees)], category=category,
            affected_service=service, impact=spec.impact, urgency=spec.urgency,
            affected_users=spec.users, priority=result.priority, priority_score=result.score,
            status=S.ASSIGNED, created_at=created, assigned_technician=tech,
            assigned_at=now - _td(1),
            sla_tracker=self._sla.create_tracker(result.priority, self._policy_for(service), created))
        snapshot, events = self._with_sla_state(snapshot, now)
        return _Built(spec, snapshot, events, None)

    def _with_sla_state(self, snapshot: IncidentSnapshot, now: datetime):
        """Ask the real SLA calculator what the tracker should say right now, and keep the
        events it reports, so the scheduler later finds nothing new to record."""
        tracker = snapshot.sla_tracker
        if tracker is None:
            return snapshot, []
        result = self._sla.evaluate(Incident.restore(snapshot), now)
        start = snapshot.created_at
        recorded_at = {
            SlaEventType.RESPONSE_VIOLATED: tracker.response_deadline,
            SlaEventType.RESOLUTION_VIOLATED: tracker.resolution_deadline,
            SlaEventType.RESPONSE_WARNING: start + (tracker.response_deadline - start) * BusinessRules.SLA_WARNING_FRACTION,
            SlaEventType.RESOLUTION_WARNING: start + (tracker.resolution_deadline - start) * BusinessRules.SLA_WARNING_FRACTION,
        }
        kinds = set(result.new_events)
        updated = SlaTracker(
            tracker.response_deadline, tracker.resolution_deadline,
            SlaEventType.RESPONSE_WARNING in kinds, SlaEventType.RESOLUTION_WARNING in kinds,
            SlaEventType.RESPONSE_VIOLATED in kinds, SlaEventType.RESOLUTION_VIOLATED in kinds,
            result.status)
        return (replace(snapshot, sla_tracker=updated),
                [(kind, recorded_at[kind].replace(microsecond=0)) for kind in result.new_events])

    # ---- saving ------------------------------------------------------------------------------
    def _save_incidents(self, built: list[_Built], now: datetime) -> None:
        """Oldest first, so ticket numbers rise with time like a real system."""
        tickets: dict[str, str] = {}
        system, admin = User.system(), self._admins[0]
        for item in built:
            snapshot = item.snapshot
            if item.spec.duplicate_of:
                snapshot = replace(snapshot, possible_duplicate_of=tickets[item.spec.duplicate_of])
            incident = self._incidents.save(Incident.restore(snapshot))
            if item.spec.key:
                tickets[item.spec.key] = incident.ticket_number
            for kind, when in item.events:
                self._sla_events.save(SlaEvent(incident_id=incident.id, event_type=kind, recorded_at=when))
            for record in self._audit_records(incident, item, system):
                self._audits.save(record)
            for note in self._notifications_for(incident, item, now, admin):
                self._notifications.save(note)

    def _audit_records(self, incident: Incident, item: _Built, system: User) -> list[AuditRecord]:
        s = incident.snapshot()
        tech, reporter, tag = s.assigned_technician, s.reporter, incident.ticket_number
        rows: list[tuple] = [(s.created_at, reporter, "CREATED", None, S.NEW,
                              f"Incident {tag} created by {reporter.full_name}")]

        def add(when, actor, action, prev, new, text):
            if when is not None:
                rows.append((when, actor, action, prev, new, text))

        if s.priority is not None:
            add(s.created_at + _td(1), system, "CLASSIFIED", S.NEW, S.CLASSIFIED,
                f"Classified as {s.category.name}; priority {s.priority.name} (score {s.priority_score})")
        if item.spec.duplicate_of:
            add(s.created_at + _td(1), system, "DUPLICATE_FLAGGED", S.NEW, S.NEW,
                f"Possibly a duplicate of {s.possible_duplicate_of}")
        if tech:
            add(s.assigned_at, system, "ASSIGNED", S.CLASSIFIED, S.ASSIGNED, f"Assigned to {tech.full_name}")
        add(s.acknowledged_at, tech, "ACKNOWLEDGED", S.ASSIGNED, S.ACKNOWLEDGED, f"{tech.full_name if tech else ''} acknowledged the incident")
        add(item.inv_at, tech, "INVESTIGATION_STARTED", S.ACKNOWLEDGED, S.IN_PROGRESS, "Investigation started")
        for note in s.notes:
            add(note.created_at, note.author, "NOTE_ADDED", S.IN_PROGRESS, S.IN_PROGRESS, note.text)
        if s.resolution:
            add(s.resolved_at, tech, "RESOLVED", S.IN_PROGRESS, S.RESOLVED, s.resolution.summary)
        add(s.verified_at, reporter, "VERIFIED", S.RESOLVED, S.VERIFIED, "Resolution verified by the reporter")
        add(s.closed_at, reporter, "CLOSED", S.VERIFIED, S.CLOSED, "Incident closed")
        if s.feedback:
            add(s.feedback.submitted_at, reporter, "FEEDBACK_SUBMITTED", S.VERIFIED, S.VERIFIED,
                f"Rated {s.feedback.rating} out of 5")
        for kind, when in item.events:
            violated = kind in (SlaEventType.RESPONSE_VIOLATED, SlaEventType.RESOLUTION_VIOLATED)
            add(when, system, "SLA_VIOLATED" if violated else "SLA_WARNING", s.status, s.status, kind.name.replace("_", " ").title())
        rows.sort(key=lambda r: r[0])
        return [AuditRecord(incident_id=incident.id, ticket_number=tag, timestamp=when,
                            actor_id=actor.id, actor_name=actor.full_name, action=action,
                            previous_status=prev, new_status=new, description=text)
                for when, actor, action, prev, new, text in rows]

    def _notifications_for(self, incident: Incident, item: _Built, now: datetime, admin: User):
        """A handful of in-app notifications for incidents that are not closed. Older ones are read."""
        s, tag, out = incident.snapshot(), incident.ticket_number, []
        if s.status is S.CLOSED:
            return out

        def add(recipient, kind, text, when):
            out.append(Notification(recipient_id=recipient.id, incident_id=incident.id, event_type=kind,
                                    channel=ChannelType.IN_APP, message=text, created_at=when,
                                    is_read=when < now - timedelta(hours=12)))

        if s.assigned_technician:
            add(s.assigned_technician, IncidentEventType.ASSIGNED, f"{tag} was assigned to you: {s.title}", s.assigned_at)
        if s.resolved_at:
            add(s.reporter, IncidentEventType.RESOLVED, f"{tag} has been resolved. Please verify the fix.", s.resolved_at)
        if item.spec.duplicate_of:
            add(admin, IncidentEventType.DUPLICATE_FLAGGED,
                f"{tag} may be a duplicate of {s.possible_duplicate_of}", s.created_at + _td(1))
        for kind, when in item.events:
            if kind in (SlaEventType.RESPONSE_VIOLATED, SlaEventType.RESOLUTION_VIOLATED):
                add(admin, IncidentEventType.SLA_VIOLATED, f"SLA violated on {tag}: {s.title}", when)
        return out


def main() -> None:
    """python -m app.persistence.seeder: seed the database named by DATABASE_PATH."""
    from app.config import Settings
    from app.domain.time_provider import SystemTimeProvider
    from app.persistence.database import Database
    from app.persistence.sqlite_audit_repository import SqliteAuditRepository
    from app.persistence.sqlite_category_repository import SqliteCategoryRepository
    from app.persistence.sqlite_incident_repository import SqliteIncidentRepository
    from app.persistence.sqlite_notification_repository import SqliteNotificationRepository
    from app.persistence.sqlite_service_repository import SqliteServiceRepository
    from app.persistence.sqlite_sla_event_repository import SqliteSlaEventRepository
    from app.persistence.sqlite_sla_policy_repository import SqliteSlaPolicyRepository
    from app.persistence.sqlite_user_repository import SqliteUserRepository

    settings = Settings.from_env()
    db = Database(settings.DATABASE_PATH)
    db.initialise()
    seeder = DemoDataSeeder(
        SqliteUserRepository(db), SqliteCategoryRepository(db), SqliteServiceRepository(db),
        SqliteSlaPolicyRepository(db), SqliteIncidentRepository(db), SqliteAuditRepository(db),
        SqliteNotificationRepository(db), SqliteSlaEventRepository(db), SystemTimeProvider())
    print("Seeded demo data." if seeder.seed_if_empty()
          else "Database already has users; nothing changed.")


if __name__ == "__main__":
    main()
