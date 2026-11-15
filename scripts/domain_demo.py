"""Live demo of the domain layer, for the video. No web, no database: just the objects.

    python scripts/domain_demo.py            (run from the repository root)
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.enums import IncidentStatus, Level, Priority  # noqa: E402
from app.domain.exceptions import ITSMError  # noqa: E402
from app.domain.intelligence.duplicate_detector import DuplicateDetector  # noqa: E402
from app.domain.intelligence.escalation_policy import EscalationPolicy  # noqa: E402
from app.domain.models.candidates import TechnicianCandidate  # noqa: E402
from app.domain.models.category import Category  # noqa: E402
from app.domain.models.incident import Incident  # noqa: E402
from app.domain.models.it_service import ITService  # noqa: E402
from app.domain.models.sla import SlaPolicy, SlaTarget  # noqa: E402
from app.domain.models.user import Employee, Technician, User  # noqa: E402
from app.domain.business_rules import BusinessRules  # noqa: E402
from app.domain.observer import IncidentObserver  # noqa: E402
from app.domain.sla.sla_calculator import SlaCalculator  # noqa: E402
from app.domain.strategies.assignment import (  # noqa: E402
    LoadBasedAssignment, SkillBasedAssignment, WeightedRecommendationStrategy,
)
from app.domain.strategies.priority import (  # noqa: E402
    PriorityInput, RuleBasedPriorityStrategy, WeightedScorePriorityStrategy,
)
from app.domain.time_provider import SimulatedTimeProvider  # noqa: E402

SYSTEM, CLOCK, CALC = User.system(), SimulatedTimeProvider(), SlaCalculator()
POLICY = SlaPolicy("Default", True, {p: SlaTarget(r, s) for p, (r, s) in BusinessRules.DEFAULT_SLA_TARGET_MINUTES.items()})

employee = Employee("emp1", "Asha Rao", "asha@example.com", "hash", "Finance", id=1)
tech = Technician("tech1", "Ravi Kumar", "ravi@example.com", "hash", {"Database"}, 4, id=2)
payment = ITService("Payment", "Payment application", Level.HIGH, id=1)
printing = ITService("Printing", "Office printers", Level.LOW, id=2)
category = Category("Application", "Application faults", "Database", id=1)


def header(text):
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def new_incident(title, description, service=payment, users=120, when=None):
    return Incident(title, description, employee, category, service, Level.HIGH, Level.HIGH,
                    users, when or CLOCK.now())


class Printer(IncidentObserver):
    """Stands in for the audit log: prints every event it hears."""

    def on_event(self, e):
        before = e.previous_status.name if e.previous_status else "-"
        print(f"  {e.timestamp:%H:%M:%S}  {e.event_type.name:<22} {before:>12} -> {e.new_status.name:<12} {e.description}")


def prioritise_and_open(incident, strategy=None):
    result = (strategy or WeightedScorePriorityStrategy()).calculate(
        PriorityInput(incident.impact, incident.urgency, incident.affected_service.business_criticality,
                      incident.affected_users))
    tracker = CALC.create_tracker(result.priority, POLICY, incident.created_at)
    incident.classify(SYSTEM, CLOCK.now(), result, tracker)
    return result


# ------------------------------------------------------------------ 1
header("1. The lifecycle, step by step (every line is an event an observer hears)")
incident = new_incident("Payment application unavailable", "Users are unable to complete transactions")
incident.assign_identity(1, "INC-1001")
incident.add_observer(Printer())
incident.record_creation(employee, CLOCK.now())
result = prioritise_and_open(incident)
print(f"  priority explanation: {result.explanation}")
incident.assign_to(SYSTEM, CLOCK.now(), tech, 0)
incident.acknowledge(tech, CLOCK.now())
incident.start_investigation(tech, CLOCK.now())
incident.resolve(tech, CLOCK.now(), "Restarted the payment DB pool", "Connection pool was exhausted")
incident.verify(employee, CLOCK.now())
incident.close(employee, CLOCK.now())
incident.submit_feedback(employee, CLOCK.now(), 5, "Fast fix")

# ------------------------------------------------------------------ 2
header("2. Illegal moves fail by construction (State pattern)")
fresh = new_incident("Printer out of paper", "Third floor printer", printing, 1)
for label, action in [
    ("NEW -> CLOSED (skipping every step)", lambda: fresh.close(employee, CLOCK.now())),
    ("acknowledging an incident that is still NEW", lambda: fresh.acknowledge(tech, CLOCK.now())),
]:
    try:
        action()
    except ITSMError as error:
        print(f"  {label}\n      {type(error).__name__}: {error}")
assigned = new_incident("Database slow", "Queries time out")
prioritise_and_open(assigned)
assigned.assign_to(SYSTEM, CLOCK.now(), tech, 0)
try:
    assigned.acknowledge(employee, CLOCK.now())
except ITSMError as error:
    print(f"  the reporter acknowledging someone else's work\n      {type(error).__name__}: {error}")
try:
    prioritise_and_open(fresh)
    fresh.assign_to(SYSTEM, CLOCK.now(), tech, BusinessRules.MAX_ACTIVE_INCIDENTS)
except ITSMError as error:
    print(f"  assigning to a technician who already has {BusinessRules.MAX_ACTIVE_INCIDENTS} active incidents\n      {type(error).__name__}: {error}")

# ------------------------------------------------------------------ 3
header("3. Swapping the priority strategy (Strategy pattern): same input, two policies")
data = PriorityInput(Level.HIGH, Level.LOW, Level.HIGH, 5)
for strategy in (WeightedScorePriorityStrategy(), RuleBasedPriorityStrategy()):
    r = strategy.calculate(data)
    print(f"  {strategy.name:<15} -> {r.priority.name} ({r.priority.label}): {r.explanation}")

# ------------------------------------------------------------------ 4
header("4. Duplicate detection on the three payment reports (and one unrelated report)")
reports = [
    new_incident("Payment application unavailable", "Users are unable to complete transactions in the payment application"),
    new_incident("Payment transaction failing", "Transaction attempts keep failing with an error at checkout"),
    new_incident("Unable to make payment", "I cannot pay for my order at checkout"),
    new_incident("Printer out of paper", "The third floor printer shows an out of paper message", printing, 1),
]
for n, r in enumerate(reports, start=11):
    r.assign_identity(n, f"INC-10{n}")
detector = DuplicateDetector()
for r in reports:
    matches = detector.find_similar(r, reports)
    shown = ", ".join(f"{m.other_ticket_number} ({m.score:.2f})" for m in matches) or "none"
    print(f"  {r.ticket_number} {r.title!r:<40} flags: {shown}")

# ------------------------------------------------------------------ 5
header("5. SLA clocks on a P1 (response 5 min, resolution 30 min), fast-forwarded")
sla_clock = SimulatedTimeProvider()
p1 = new_incident("Payment down", "Cannot pay", when=sla_clock.now())
prioritise_and_open(p1)
p1.assign_to(SYSTEM, sla_clock.now(), tech, 0)
p1.add_observer(Printer())
elapsed = 0
for minutes in (2, 4, 6, 25, 31):
    sla_clock.advance(timedelta(minutes=minutes - elapsed))
    elapsed = minutes
    check = CALC.evaluate(p1, sla_clock.now())
    p1.apply_sla_result(sla_clock.now(), check)
    print(f"  after {minutes:>2} min: status {check.status.name:<9} new events: {[e.name for e in check.new_events] or '-'}")
print("  (a violation is sticky: once VIOLATED, the status stays VIOLATED)")

# ------------------------------------------------------------------ 6
header("6. Automatic escalation of an unacknowledged P1 (checked at 6, 16 and 26 minutes)")
esc_clock = SimulatedTimeProvider()
p1b = new_incident("Payment down again", "Cannot pay", when=esc_clock.now())
prioritise_and_open(p1b)
p1b.assign_to(SYSTEM, esc_clock.now(), tech, 0)
p1b.add_observer(Printer())
policy, elapsed = EscalationPolicy(), 0
for minutes in (6, 16, 26, 36):
    esc_clock.advance(timedelta(minutes=minutes - elapsed))
    elapsed = minutes
    decision = policy.evaluate(p1b, esc_clock.now())
    if decision:
        p1b.escalate(SYSTEM, esc_clock.now(), decision)
        print(f"  after {minutes:>2} min: escalate to {decision.new_level.name} (notify {decision.target_admin_level.name})")
    else:
        print(f"  after {minutes:>2} min: nothing new (already at {p1b.escalation_level.name})")

# ------------------------------------------------------------------ 7
header("7. Three assignment strategies on the same technicians")
db = Category("Database", "DB faults", "Database", id=2)
case = Incident("Database down", "Cannot connect", employee, db, payment, Level.HIGH, Level.HIGH, 5, CLOCK.now())
staff = [
    TechnicianCandidate(Technician("t1", "Tara S", "t1@x.com", "h", {"Database"}, 2, id=11), 3, 0),
    TechnicianCandidate(Technician("t2", "Omar K", "t2@x.com", "h", {"Database", "Network"}, 8, id=12), 1, 3),
    TechnicianCandidate(Technician("t3", "Lena P", "t3@x.com", "h", {"Network"}, 10, id=13), 0, 0),
    TechnicianCandidate(Technician("t4", "Dev R", "t4@x.com", "h", {"Database"}, 5, id=14), 1, 5),
]
for strategy in (SkillBasedAssignment(), LoadBasedAssignment(), WeightedRecommendationStrategy()):
    ranked = strategy.rank(case, staff)
    pick = ranked[0]
    print(f"  {strategy.name:<24} picks {pick.technician.full_name:<8} score {pick.score:>5}  ({'; '.join(pick.reasons)})")
print()
