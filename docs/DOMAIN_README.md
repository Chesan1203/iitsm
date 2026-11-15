# Domain layer: read me first

`app/domain/` is the brain of the system: pure Python, standard library only, no web, no database. Tagged `domain-v1.0` (see git tags for later fixes). If something looks wrong, start with the debugging map at the end.

How to check it is healthy: `pytest tests/domain tests/test_architecture.py tests/test_domain_imports.py`. To see it work: `python scripts/domain_demo.py`.

Related documents: `docs/oop_and_patterns.md` (concepts and patterns), `docs/business_rules.md` (algorithms), `docs/domain_decisions.md` (lifecycle decisions), `docs/class_diagram.puml` and `class_diagram_*.png`, `CONTRACT.md` (every signature).

## Foundations (`app/domain/`)

| Class / module | What it does | Pattern or concept |
|---|---|---|
| `BusinessRules` | Every business constant (thresholds, SLA targets, weights, windows) in one place | Single source of truth |
| `Role`, `AdminLevel`, `Level`, `Priority`, `IncidentStatus`, `SlaStatus`, `NoteType`, `ChannelType`, `EscalationLevel`, `SlaEventType`, `IncidentEventType` | The fixed vocabularies of the system (`Priority.label` gives Critical/High/Medium/Low) | Enums |
| `ITSMError` | Base of every application error; carries a readable `message` | Exception hierarchy |
| `InvalidLoginError`, `UnauthorizedOperationError`, `InvalidStateTransitionError`, `TechnicianUnavailableError`, `WorkloadExceededError`, `MissingSlaConfigurationError`, `DuplicateIncidentError`, `PersistenceError` | One error per way things can go wrong, raised by the domain or by the layers above | Custom exceptions |
| `NotFoundError`, `IncidentNotFoundError`, `ServiceNotFoundError`, `CategoryNotFoundError`, `UserNotFoundError` | A looked-up object does not exist | Exception hierarchy |
| `InvalidInputError` | Bad or missing input; also carries the `field` name | Validation |
| `TimeProvider` | The only source of "now": a one-method interface | Interface, Strategy |
| `SystemTimeProvider` | The real clock | Polymorphism |
| `SimulatedTimeProvider` | Real clock plus an offset, so the demo can fast-forward to trigger SLA breaches | Polymorphism |

## Entities and value objects (`app/domain/models/`)

| Class | What it does | Pattern or concept |
|---|---|---|
| `Entity` | Base of everything with a database id; the id can be assigned once | Inheritance, encapsulation |
| `User` | Abstract person: username, role, password hash, active flag; `User.system()` gives the automated actor | Abstract class |
| `Employee`, `Technician`, `Administrator` | The three human roles (department; skills, experience, availability, workload limit; admin level) | Inheritance |
| `SystemUser` | The automated actor (id 0) that classifies incidents and runs the jobs; cannot be changed | Inheritance, Null-object-like actor |
| `ITService` | A service with its business criticality and a reference to its SLA policy | Association |
| `Category` | An incident category and the skill needed to handle it | Entity |
| `SlaTarget`, `SlaPolicy` | Response/resolution minutes per priority; a policy owns its targets and answers `target_for(priority)` | Composition |
| `SlaTracker` | The two deadlines, warning/violation flags and SLA status of one incident | Composition (owned by `Incident`) |
| `InvestigationNote`, `Resolution`, `Feedback` | A note, the resolution and the reporter's rating; immutable | Composition, value objects |
| `Incident` | The central object: validates itself, holds the data, delegates every action to its current state, announces events, converts to and from a snapshot | State (context), Observer (subject), Encapsulation |
| `IncidentSnapshot` | A plain copy of every incident field, used by persistence and seed data to save and rebuild an incident | Memento-like value object |
| `AuditRecord`, `Notification`, `SlaEvent` | Immutable records of what happened, who was told, and which SLA events were recorded | Value objects |
| `TechnicianCandidate`, `RankedTechnician` | Input and output of assignment: a technician with their counts; a technician with a score and reasons | Value objects |

## Lifecycle: State and Observer (`app/domain/state/`, `observer.py`, `events.py`)

| Class | What it does | Pattern or concept |
|---|---|---|
| `IncidentState` | Abstract base: every action raises `InvalidStateTransitionError` unless a state overrides it | State pattern (abstract state), Template Method |
| `OpenState` | The actions allowed in every state except CLOSED (notes, escalation, priority change, duplicate flag, SLA result) | Inheritance |
| `NewState`, `ClassifiedState`, `AssignedState`, `AcknowledgedState`, `InProgressState`, `ResolvedState`, `VerifiedState` | One class per status; each overrides only the actions legal there | State pattern (concrete states) |
| `ClosedState` | Terminal; only the reporter's one-time feedback is still accepted | State pattern |
| `IncidentStateFactory` | Hands out the one shared state object for a status | Factory, Flyweight |
| `permissions` (module of functions) | `require_system`, `require_admin`, `require_assigned_technician`, `require_reporter`, ... raise `UnauthorizedOperationError` | Guard clauses |
| `IncidentObserver` | Interface for anything that wants to hear about incident changes | Observer pattern (observer), Interface |
| `IncidentEvent` | Immutable description of one change: who, what, previous and new status, when | Observer pattern (event) |

## Strategies and intelligence (`strategies/`, `sla/`, `intelligence/`)

| Class | What it does | Pattern or concept |
|---|---|---|
| `PriorityStrategy` | Interface: `calculate(PriorityInput)` returns a `PriorityResult` | Strategy pattern, Interface |
| `PriorityInput`, `PriorityResult` | The factors going in; the score, priority and explanation coming out | Value objects |
| `WeightedScorePriorityStrategy` | impact x urgency x criticality, thresholds, bump for 50+ affected users | Strategy (concrete) |
| `RuleBasedPriorityStrategy` | HIGH criticality and HIGH impact is always P1, otherwise the weighted score | Strategy, Composition |
| `AssignmentStrategy` | Abstract: `rank` and `name` per strategy; `select` is the first of `rank` | Strategy pattern, Template Method |
| `SkillBasedAssignment`, `LoadBasedAssignment` | Least-loaded technician with the skill; least-loaded technician | Strategy (concrete) |
| `WeightedRecommendationStrategy` | Scores technicians out of 100 on skill, load, experience and history, with reasons (the smart recommendation) | Strategy (concrete), intelligent feature |
| `SlaCalculator`, `SlaCheckResult` | Builds trackers; evaluates an incident at a time and returns the status and only the new warning/violation events | Pure function style |
| `DuplicateDetector`, `DuplicateMatch` | Flags possibly duplicate incidents using synonym-normalised word sets and the Jaccard index | Intelligent feature |
| `EscalationPolicy`, `EscalationDecision` | Decides when an unacknowledged P1 moves up the chain, and to whom | Intelligent feature, stateless policy |
| `CorrelationDetector`, `CorrelationGroup` | Groups unresolved incidents of the last hour by service; 3 or more is a probable service problem | Intelligent feature |

## Debugging map: where to look

| Symptom | Look at |
|---|---|
| An action is refused with "Cannot ... an incident that is X" | The lifecycle table in `state/states.py` and `tests/domain/test_state_machine.py` (`LEGAL`) |
| "Only the assigned technician / reporter / administrator can ..." | `state/permissions.py`; users are compared by id, so unsaved users never match |
| An action succeeds but no audit record or notification appears | Observers are not saved: re-attach them after every load (`Incident.add_observer`); a failing observer is only logged (`Incident._fire`) |
| Wrong priority | `strategies/priority.py` and `BusinessRules`; the result's `explanation` says how it was reached |
| Wrong or repeated SLA warning, or VIOLATED showing unexpectedly | `sla/sla_calculator.py` (`_clock`, `evaluate`) and `docs/business_rules.md` section 2; violations are sticky and a late acknowledgement counts |
| A technician is not offered | `strategies/assignment.py`: the technician must be active, available and below their `max_workload` |
| A duplicate is missed or wrongly flagged | `intelligence/duplicate_detector.py`: add a synonym group or check `tokens(...)`; the score threshold is `BusinessRules.DUPLICATE_THRESHOLD` |
| Escalation not happening | The incident must be P1, still ASSIGNED, past its response deadline (`intelligence/escalation_policy.py`) |
| `TypeError` when comparing times | A time zone leaked in: all domain times are naive (`require_naive_datetime`) |
| A new import breaks a layer rule | `tests/test_architecture.py` names the file and line |
