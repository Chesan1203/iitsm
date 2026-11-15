# CONTRACT (frozen at tag `contract-v1`)

Generated from the skeleton code, so it is exact. The prose origin is Chapter 5 of the project plan.
Paste this file into your AI chat as "the contract". Do not rename anything here. To propose a change,
add a line to `CONTRACT_CHANGES.md` (see the protocol there).

## Layers and import rules (enforced by `tests/test_architecture.py`)
| Folder | Owner | May import |
|---|---|---|
| `app/domain/` | P1 | standard library only (no sqlite3, sockets, http, threads) |
| `app/ports/` | frozen | standard library, domain |
| `app/persistence/` | P2 | domain, ports, bcrypt, sqlite3 |
| `app/services/` | P3 | domain, ports, bcrypt, apscheduler (only `services/wiring.py` may also import persistence) |
| `app/web/` | P4 | ports; from domain only `enums`, `exceptions`, `models`; FastAPI stack |
| `app/config.py` | skeleton | standard library only; importable by persistence, services, web |
| `app/main.py` | skeleton | anything (composition entry point; two-line edits only) |

Also enforced: domain never reads the clock (take `at`/`now` as a parameter), domain has no `@property.setter`,
`sqlite3` appears only in persistence.

## Conventions
- Ids are `int`, `None` until first saved. Times are naive `datetime` (local). Dates in search filters are `date`.
- Entities: private fields, read-only properties, no setters. Ids are write-once via `assign_id` (incidents: `assign_identity`).
- Frozen dataclasses (`AuditRecord`, `Notification`, `SlaEvent`, `InvestigationNote`, ...) are built with keyword arguments;
  repositories fill the id with `dataclasses.replace(record, id=n)`.
- `find_*` returns `None` / empty list when nothing matches; services turn `None` into a `NotFoundError`.
- `save` inserts when `id is None`, otherwise updates, and returns the saved object. Incidents load WITHOUT observers.
- Order of checks inside every incident action: (1) legal in the current state? `InvalidStateTransitionError`;
  (2) actor allowed? `UnauthorizedOperationError`; (3) data valid? `InvalidInputError` / workload errors.
- Every service method except `login` and `register_employee` takes the acting `User` first.

## Additions beyond plan Chapter 5 (needed to make the skeleton work; all additive)
- `Entity` base with write-once `assign_id`; `Incident.assign_identity(id, ticket_number)`.
- `User.activate()`, `User.deactivate()`, `Technician.set_available(bool)`; `User.describe()`.
- `SystemUser` (id 0, role ADMINISTRATOR, unusable password hash) returned by `User.system()`.
- `ITService`, `Category`, `SlaPolicy` are immutable: to update, build a new object with the same `id` and `save` it.
- `IncidentSnapshot` holds objects (reporter, technician, service, category), not ids; construct with keywords.
- `SlaTracker.copy()`; `snapshot()` returns a copy of the tracker so it is never aliased.
- `IncidentState` subclasses expose `status`; state objects are derived from `incident.status` through
  `IncidentStateFactory.for_status` on demand (not stored), which is what makes `Incident.restore` work for any status.
- `Incident.has_pending_info_request` (read-only): true when the latest information note is an unanswered INFO_REQUEST.
- Permission helpers in `app/domain/state/permissions.py`; state behaviour decisions in `docs/domain_decisions.md`.
- `SlaEventType.WARNING` was split into `RESPONSE_WARNING` and `RESOLUTION_WARNING` (T6, see `CONTRACT_CHANGES.md` and `docs/business_rules.md`).
- `AssignmentStrategy.select` is concrete (the first technician of `rank`, or None); strategies implement `rank` and `name`.
- `TechnicianCandidate` validates its fields; `EscalationPolicy`, `DuplicateDetector` and `CorrelationDetector` semantics are in `docs/business_rules.md`.
- `SimulatedTimeProvider.advance(timedelta)` / `reset()` / `offset` (implemented now, task T1).
- Strategy names (used as registry keys and in the admin UI): priority `weighted_score`, `rule_based`;
  assignment `skill_based`, `load_based`, `weighted_recommendation`.
- Admin service return types: mutators return the saved object; `set_*_strategy` returns `None`;
  `advance_time` / `reset_time` return the new `datetime`; `run_*_check_now` return `int`.

## Known open points (decide before relying on them)
- `SlaPolicyRequest` has no `id`, so `save_sla_policy` cannot say which policy to update.
- `list_for_user(actor, limit)` has no default `limit`.

## Settings (`app/config.py`)
`ITSM_MODE` real|stub (default real), `DATABASE_PATH` (data/iitsm.db), `EMAIL_LOG_PATH` (logs/emails.log),
`SECRET_KEY`, `SIMULATED_TIME` (True), `SEED_DEMO_DATA` (True), `ENABLE_SCHEDULER` (True).

## Enums  <sub>app/domain/enums.py</sub>

- `AdminLevel`: TEAM_LEAD, SYSTEM_ADMIN, IT_MANAGER
- `ChannelType`: IN_APP, EMAIL
- `EscalationLevel`: TECHNICIAN=0, TEAM_LEAD=1, SYSTEM_ADMIN=2, IT_MANAGER=3
- `IncidentEventType`: CREATED, CLASSIFIED, ASSIGNED, REASSIGNED, ACKNOWLEDGED, INVESTIGATION_STARTED, NOTE_ADDED, INFO_REQUESTED, INFO_RESPONDED, RESOLVED, RESOLUTION_REJECTED, VERIFIED, CLOSED, PRIORITY_CHANGED, ESCALATED, SLA_WARNING, SLA_VIOLATED, DUPLICATE_FLAGGED, FEEDBACK_SUBMITTED
- `IncidentStatus`: NEW, CLASSIFIED, ASSIGNED, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, VERIFIED, CLOSED
- `Level`: LOW=1, MEDIUM=2, HIGH=3
- `NoteType`: INVESTIGATION, INFO_REQUEST, INFO_RESPONSE
- `Priority`: P1=1, P2=2, P3=3, P4=4
- `Role`: EMPLOYEE, TECHNICIAN, ADMINISTRATOR
- `SlaEventType`: RESPONSE_WARNING, RESOLUTION_WARNING, RESPONSE_VIOLATED, RESOLUTION_VIOLATED
- `SlaStatus`: ON_TRACK, WARNING, VIOLATED, MET

`Priority.label`: P1 Critical, P2 High, P3 Medium, P4 Low.

## Exceptions  <sub>app/domain/exceptions.py</sub>
Every exception has `.message`; `InvalidInputError` also has `.field`.

- `CategoryNotFoundError(NotFoundError)`
- `DuplicateIncidentError(ITSMError)`
- `ITSMError(Exception)`
- `IncidentNotFoundError(NotFoundError)`
- `InvalidInputError(ITSMError)`
- `InvalidLoginError(ITSMError)`
- `InvalidStateTransitionError(ITSMError)`
- `MissingSlaConfigurationError(ITSMError)`
- `NotFoundError(ITSMError)`
- `PersistenceError(ITSMError)`
- `ServiceNotFoundError(NotFoundError)`
- `TechnicianUnavailableError(ITSMError)`
- `UnauthorizedOperationError(ITSMError)`
- `UserNotFoundError(NotFoundError)`
- `WorkloadExceededError(ITSMError)`

## Business rules  <sub>app/domain/business_rules.py</sub>
`BusinessRules` constants: `LEVEL_MIN`, `LEVEL_MAX`, `P1_MIN_SCORE`, `P2_MIN_SCORE`, `P3_MIN_SCORE`, `AFFECTED_USERS_BUMP_THRESHOLD`, `DEFAULT_SLA_TARGET_MINUTES`, `SLA_WARNING_FRACTION`, `MAX_ACTIVE_INCIDENTS`, `WEIGHT_SKILL`, `WEIGHT_LOAD`, `WEIGHT_EXPERIENCE`, `WEIGHT_SERVICE_HISTORY`, `EXPERIENCE_CAP_YEARS`, `SERVICE_HISTORY_CAP`, `EXACT_RESUBMISSION_WINDOW_MINUTES`, `DUPLICATE_LOOKBACK_HOURS`, `DUPLICATE_TEXT_WEIGHT`, `DUPLICATE_SERVICE_WEIGHT`, `DUPLICATE_THRESHOLD`, `CORRELATION_MIN_INCIDENTS`, `CORRELATION_WINDOW_MINUTES`, `ESCALATION_STEP_MINUTES`, `SCHEDULER_INTERVAL_SECONDS`, `MIN_PASSWORD_LENGTH`, `DEMO_PASSWORD`

## Domain entities and value objects

### `User`(Entity, ABC)  <sub>app.domain.models.user</sub>
Constructor: `User(username: str, full_name: str, email: str, password_hash: str, role: app.domain.enums.Role, *, id: int | None = None, active: bool = True)`
- `system() -> 'User'` (staticmethod)
- `username` (property)
- `full_name` (property)
- `email` (property)
- `password_hash` (property)
- `role` (property)
- `active` (property)
- `is_system` (property)
- `activate() -> None`
- `deactivate() -> None`
- `describe() -> str`

### `Employee`(User)  <sub>app.domain.models.user</sub>
Constructor: `Employee(username: str, full_name: str, email: str, password_hash: str, department: str = '', *, id: int | None = None, active: bool = True)`
- `department` (property)
- `describe() -> str`

### `Technician`(User)  <sub>app.domain.models.user</sub>
Constructor: `Technician(username: str, full_name: str, email: str, password_hash: str, skills=(), experience_years: int = 0, available: bool = True, max_workload: int = 5, *, id: int | None = None, active: bool = True)`
- `skills` (property)
- `experience_years` (property)
- `available` (property)
- `max_workload` (property)
- `set_available(available: bool) -> None`
- `describe() -> str`

### `Administrator`(User)  <sub>app.domain.models.user</sub>
Constructor: `Administrator(username: str, full_name: str, email: str, password_hash: str, admin_level: app.domain.enums.AdminLevel, *, id: int | None = None, active: bool = True)`
- `admin_level` (property)
- `describe() -> str`

### `ITService`(Entity)  <sub>app.domain.models.it_service</sub>
Constructor: `ITService(name: str, description: str, business_criticality: app.domain.enums.Level, sla_policy_id: int | None = None, active: bool = True, *, id: int | None = None)`
- `name` (property)
- `description` (property)
- `business_criticality` (property)
- `sla_policy_id` (property)
- `active` (property)

### `Category`(Entity)  <sub>app.domain.models.category</sub>
Constructor: `Category(name: str, description: str, required_skill: str, active: bool = True, *, id: int | None = None)`
- `name` (property)
- `description` (property)
- `required_skill` (property)
- `active` (property)

### `SlaTarget`  <sub>app.domain.models.sla</sub>
Fields: `response_minutes`, `resolution_minutes`

### `SlaPolicy`(Entity)  <sub>app.domain.models.sla</sub>
Constructor: `SlaPolicy(name: str, is_default: bool = False, targets: dict | None = None, *, id: int | None = None)`
- `name` (property)
- `is_default` (property)
- `targets` (property)
- `target_for(priority: app.domain.enums.Priority) -> app.domain.models.sla.SlaTarget`

### `SlaEvent`  <sub>app.domain.models.sla</sub>
Fields: `id`, `incident_id`, `event_type`, `recorded_at`

### `SlaTracker`  <sub>app.domain.models.incident_parts</sub>
Constructor: `SlaTracker(response_deadline: datetime.datetime, resolution_deadline: datetime.datetime, response_warned: bool = False, resolution_warned: bool = False, response_violated: bool = False, resolution_violated: bool = False, status: app.domain.enums.SlaStatus = <SlaStatus.ON_TRACK: 'ON_TRACK'>)`
- `response_deadline` (property)
- `resolution_deadline` (property)
- `response_warned` (property)
- `resolution_warned` (property)
- `response_violated` (property)
- `resolution_violated` (property)
- `status` (property)
- `copy() -> 'SlaTracker'`

### `InvestigationNote`  <sub>app.domain.models.incident_parts</sub>
Fields: `id`, `author`, `note_type`, `text`, `created_at`

### `Resolution`  <sub>app.domain.models.incident_parts</sub>
Fields: `summary`, `details`, `resolved_by`, `resolved_at`

### `Feedback`  <sub>app.domain.models.incident_parts</sub>
Fields: `rating`, `comment`, `submitted_at`

### `AuditRecord`  <sub>app.domain.models.audit</sub>
Fields: `id`, `incident_id`, `ticket_number`, `timestamp`, `actor_id`, `actor_name`, `action`, `previous_status`, `new_status`, `description`

### `Notification`  <sub>app.domain.models.notification</sub>
Fields: `id`, `recipient_id`, `incident_id`, `event_type`, `channel`, `message`, `created_at`, `is_read`

### `TechnicianCandidate`  <sub>app.domain.models.candidates</sub>
Fields: `technician`, `active_incident_count`, `resolved_on_this_service_count`

### `RankedTechnician`  <sub>app.domain.models.candidates</sub>
Fields: `technician`, `score`, `reasons`

### `IncidentSnapshot`  <sub>app.domain.models.snapshot</sub>
Fields: `id`, `ticket_number`, `title`, `description`, `reporter`, `category`, `affected_service`, `impact`, `urgency`, `affected_users`, `priority`, `priority_score`, `status`, `created_at`, `assigned_technician`, `assigned_at`, `acknowledged_at`, `resolved_at`, `verified_at`, `closed_at`, `escalation_level`, `possible_duplicate_of`, `notes`, `resolution`, `feedback`, `sla_tracker`

### `IncidentEvent`  <sub>app.domain.events</sub>
Fields: `incident`, `event_type`, `actor`, `previous_status`, `new_status`, `description`, `timestamp`

### `IncidentObserver`(ABC)  <sub>app.domain.observer</sub>
- `on_event(event: app.domain.events.IncidentEvent) -> None`

## Incident  <sub>app/domain/models/incident.py</sub>

Constructor: `Incident(title: 'str', description: 'str', reporter: 'User', category: 'Category', affected_service: 'ITService', impact: 'Level', urgency: 'Level', affected_users: 'int', created_at: 'datetime')`

Read-only properties: `ticket_number`, `title`, `description`, `reporter`, `category`, `affected_service`, `impact`, `urgency`, `affected_users`, `priority`, `priority_score`, `status`, `created_at`, `assigned_technician`, `assigned_at`, `acknowledged_at`, `resolved_at`, `verified_at`, `closed_at`, `escalation_level`, `possible_duplicate_of`, `resolution`, `feedback`, `sla_tracker`, `notes`, `is_open`, `is_active`, `has_pending_info_request`

Plumbing: `assign_identity(id: 'int', ticket_number: 'str') -> 'None'`, `add_observer(observer: 'IncidentObserver') -> 'None'`, `snapshot() -> 'IncidentSnapshot'`, `restore(cls, snapshot: 'IncidentSnapshot') -> "'Incident'"`

Behaviour methods (each delegates to the current state object):
- `record_creation(actor: 'User', at: 'datetime') -> 'None'`
- `classify(actor: 'User', at: 'datetime', priority_result: 'PriorityResult', sla_tracker: 'SlaTracker') -> 'None'`
- `assign_to(actor: 'User', at: 'datetime', technician: 'Technician', active_count: 'int') -> 'None'`
- `reassign(actor: 'User', at: 'datetime', technician: 'Technician', active_count: 'int') -> 'None'`
- `acknowledge(actor: 'User', at: 'datetime') -> 'None'`
- `start_investigation(actor: 'User', at: 'datetime') -> 'None'`
- `add_note(actor: 'User', at: 'datetime', text: 'str', note_type: 'NoteType') -> 'None'`
- `request_info(actor: 'User', at: 'datetime', question: 'str') -> 'None'`
- `respond_to_info(actor: 'User', at: 'datetime', answer: 'str') -> 'None'`
- `resolve(actor: 'User', at: 'datetime', summary: 'str', details: 'str') -> 'None'`
- `verify(actor: 'User', at: 'datetime') -> 'None'`
- `reject_resolution(actor: 'User', at: 'datetime', reason: 'str') -> 'None'`
- `close(actor: 'User', at: 'datetime') -> 'None'`
- `submit_feedback(actor: 'User', at: 'datetime', rating: 'int', comment: 'str') -> 'None'`
- `escalate(actor: 'User', at: 'datetime', decision: 'EscalationDecision') -> 'None'`
- `change_priority(actor: 'User', at: 'datetime', priority: 'Priority', reason: 'str', new_sla_tracker: 'SlaTracker') -> 'None'`
- `mark_possible_duplicate(actor: 'User', at: 'datetime', other_ticket_number: 'str', score: 'float') -> 'None'`
- `apply_sla_result(at: 'datetime', result: 'SlaCheckResult') -> 'None'`

## Domain logic interfaces

### `TimeProvider`(ABC)  <sub>app.domain.time_provider</sub>
- `now() -> datetime.datetime`

### `SystemTimeProvider`(TimeProvider)  <sub>app.domain.time_provider</sub>
- `now() -> datetime.datetime`

### `SimulatedTimeProvider`(TimeProvider)  <sub>app.domain.time_provider</sub>
Constructor: `SimulatedTimeProvider()`
- `offset` (property)
- `now() -> datetime.datetime`
- `advance(delta: datetime.timedelta) -> None`
- `reset() -> None`

### `PriorityInput`  <sub>app.domain.strategies.priority</sub>
Fields: `impact`, `urgency`, `criticality`, `affected_users`

### `PriorityResult`  <sub>app.domain.strategies.priority</sub>
Fields: `score`, `priority`, `explanation`

### `PriorityStrategy`(ABC)  <sub>app.domain.strategies.priority</sub>
- `calculate(data: app.domain.strategies.priority.PriorityInput) -> app.domain.strategies.priority.PriorityResult`
- `name` (property)

### `WeightedScorePriorityStrategy`(PriorityStrategy)  <sub>app.domain.strategies.priority</sub>
- `name` (property)
- `calculate(data: app.domain.strategies.priority.PriorityInput) -> app.domain.strategies.priority.PriorityResult`

### `RuleBasedPriorityStrategy`(PriorityStrategy)  <sub>app.domain.strategies.priority</sub>
Constructor: `RuleBasedPriorityStrategy()`
- `name` (property)
- `calculate(data: app.domain.strategies.priority.PriorityInput) -> app.domain.strategies.priority.PriorityResult`

### `AssignmentStrategy`(ABC)  <sub>app.domain.strategies.assignment</sub>
- `rank(incident: 'Incident', candidates: 'list[TechnicianCandidate]') -> 'list[RankedTechnician]'`
- `name` (property)
- `select(incident: 'Incident', candidates: 'list[TechnicianCandidate]') -> 'Technician | None'`

### `SkillBasedAssignment`(AssignmentStrategy)  <sub>app.domain.strategies.assignment</sub>
- `name` (property)
- `rank(incident, candidates)`

### `LoadBasedAssignment`(AssignmentStrategy)  <sub>app.domain.strategies.assignment</sub>
- `name` (property)
- `rank(incident, candidates)`

### `WeightedRecommendationStrategy`(AssignmentStrategy)  <sub>app.domain.strategies.assignment</sub>
- `name` (property)
- `rank(incident, candidates)`

### `SlaCheckResult`  <sub>app.domain.sla.sla_calculator</sub>
Fields: `status`, `new_events`

### `SlaCalculator`  <sub>app.domain.sla.sla_calculator</sub>
- `create_tracker(priority: 'Priority', policy: 'SlaPolicy', start: 'datetime') -> 'SlaTracker'`
- `evaluate(incident: 'Incident', now: 'datetime') -> 'SlaCheckResult'`

### `DuplicateMatch`  <sub>app.domain.intelligence.duplicate_detector</sub>
Fields: `other_ticket_number`, `score`

### `DuplicateDetector`  <sub>app.domain.intelligence.duplicate_detector</sub>
- `find_similar(incident: 'Incident', recent_incidents: 'list[Incident]') -> 'list[DuplicateMatch]'`

### `CorrelationGroup`  <sub>app.domain.intelligence.correlation_detector</sub>
Fields: `service`, `incidents`, `is_probable_service_problem`

### `CorrelationDetector`  <sub>app.domain.intelligence.correlation_detector</sub>
- `find_groups(open_incidents: 'list[Incident]', now: 'datetime') -> 'list[CorrelationGroup]'`

### `EscalationDecision`  <sub>app.domain.intelligence.escalation_policy</sub>
Fields: `new_level`, `target_admin_level`, `reason`

### `EscalationPolicy`  <sub>app.domain.intelligence.escalation_policy</sub>
- `evaluate(incident: 'Incident', now: 'datetime') -> 'EscalationDecision | None'`

### `IncidentState`(ABC)  <sub>app.domain.state.incident_state</sub>
- `status` (property)
- `record_creation(incident: 'Incident', actor: 'User', at: 'datetime') -> 'None'`
- `classify(incident: 'Incident', actor: 'User', at: 'datetime', priority_result: 'PriorityResult', sla_tracker: 'SlaTracker') -> 'None'`
- `assign_to(incident: 'Incident', actor: 'User', at: 'datetime', technician: 'Technician', active_count: 'int') -> 'None'`
- `reassign(incident: 'Incident', actor: 'User', at: 'datetime', technician: 'Technician', active_count: 'int') -> 'None'`
- `acknowledge(incident: 'Incident', actor: 'User', at: 'datetime') -> 'None'`
- `start_investigation(incident: 'Incident', actor: 'User', at: 'datetime') -> 'None'`
- `add_note(incident: 'Incident', actor: 'User', at: 'datetime', text: 'str', note_type: 'NoteType') -> 'None'`
- `request_info(incident: 'Incident', actor: 'User', at: 'datetime', question: 'str') -> 'None'`
- `respond_to_info(incident: 'Incident', actor: 'User', at: 'datetime', answer: 'str') -> 'None'`
- `resolve(incident: 'Incident', actor: 'User', at: 'datetime', summary: 'str', details: 'str') -> 'None'`
- `verify(incident: 'Incident', actor: 'User', at: 'datetime') -> 'None'`
- `reject_resolution(incident: 'Incident', actor: 'User', at: 'datetime', reason: 'str') -> 'None'`
- `close(incident: 'Incident', actor: 'User', at: 'datetime') -> 'None'`
- `submit_feedback(incident: 'Incident', actor: 'User', at: 'datetime', rating: 'int', comment: 'str') -> 'None'`
- `escalate(incident: 'Incident', actor: 'User', at: 'datetime', decision: 'EscalationDecision') -> 'None'`
- `change_priority(incident: 'Incident', actor: 'User', at: 'datetime', priority: 'Priority', reason: 'str', new_sla_tracker: 'SlaTracker') -> 'None'`
- `mark_possible_duplicate(incident: 'Incident', actor: 'User', at: 'datetime', other_ticket_number: 'str', score: 'float') -> 'None'`
- `apply_sla_result(incident: 'Incident', at: 'datetime', result: 'SlaCheckResult') -> 'None'`

### `IncidentStateFactory`  <sub>app.domain.state.state_factory</sub>
- `for_status(status: app.domain.enums.IncidentStatus) -> app.domain.state.incident_state.IncidentState` (staticmethod)

State classes (app/domain/state/states.py): NewState, ClassifiedState, AssignedState, AcknowledgedState, InProgressState, ResolvedState, VerifiedState, ClosedState.

## Ports: data carriers  <sub>app/ports/dto.py</sub>

### `AuditFilter`  <sub>app.ports.dto</sub>
Fields: `incident_id`, `actor_id`, `action`, `from_date`, `to_date`

### `CategoryRequest`  <sub>app.ports.dto</sub>
Fields: `name`, `description`, `required_skill`, `active`

### `CountRow`  <sub>app.ports.dto</sub>
Fields: `label`, `count`

### `CreateIncidentRequest`  <sub>app.ports.dto</sub>
Fields: `title`, `description`, `category_id`, `service_id`, `impact`, `urgency`, `affected_users`

### `CreateUserRequest`  <sub>app.ports.dto</sub>
Fields: `username`, `full_name`, `email`, `password`, `role`, `department`, `admin_level`, `skills`, `experience_years`, `max_workload`

### `IncidentSearchCriteria`  <sub>app.ports.dto</sub>
Fields: `ticket_number`, `status`, `priority`, `category_id`, `service_id`, `technician_id`, `reporter_id`, `sla_status`, `from_date`, `to_date`, `keyword`

### `OverviewReport`  <sub>app.ports.dto</sub>
Fields: `total`, `open`, `critical_open`, `resolved`, `sla_violations`

### `RegisterRequest`  <sub>app.ports.dto</sub>
Fields: `username`, `full_name`, `email`, `password`, `department`

### `ServiceRequest`  <sub>app.ports.dto</sub>
Fields: `name`, `description`, `business_criticality`, `sla_policy_id`, `active`

### `SlaPolicyRequest`  <sub>app.ports.dto</sub>
Fields: `name`, `is_default`, `targets`

### `SlaViolationRow`  <sub>app.ports.dto</sub>
Fields: `ticket_number`, `title`, `priority`, `technician_name`, `event_type`, `recorded_at`

### `WorkloadRow`  <sub>app.ports.dto</sub>
Fields: `technician_id`, `technician_name`, `active_count`, `max_workload`

## Ports: repository interfaces  <sub>app/ports/repositories.py</sub>

### `AuditRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(record: 'AuditRecord') -> 'AuditRecord'`
- `find_by_incident(incident_id: 'int') -> 'list[AuditRecord]'`
- `search(audit_filter: 'AuditFilter') -> 'list[AuditRecord]'`

### `CategoryRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(category: 'Category') -> 'Category'`
- `find_by_id(id: 'int') -> 'Category | None'`
- `find_all() -> 'list[Category]'`

### `IncidentRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(incident: 'Incident') -> 'Incident'`
- `find_by_id(id: 'int') -> 'Incident | None'`
- `find_by_ticket(ticket_number: 'str') -> 'Incident | None'`
- `search(criteria: 'IncidentSearchCriteria') -> 'list[Incident]'`
- `find_open() -> 'list[Incident]'`
- `find_unacknowledged() -> 'list[Incident]'`
- `find_recent_by_service(service_id: 'int', since: 'datetime') -> 'list[Incident]'`
- `find_recent_by_reporter(reporter_id: 'int', since: 'datetime') -> 'list[Incident]'`
- `count_active_by_technician(technician_id: 'int') -> 'int'`
- `count_resolved_by_technician_on_service(technician_id: 'int', service_id: 'int') -> 'int'`

### `NotificationRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(notification: 'Notification') -> 'Notification'`
- `find_by_recipient(user_id: 'int', limit: 'int') -> 'list[Notification]'`
- `count_unread(user_id: 'int') -> 'int'`
- `mark_read(notification_id: 'int') -> 'None'`
- `mark_all_read(user_id: 'int') -> 'None'`

### `ReportRepository`(ABC)  <sub>app.ports.repositories</sub>
- `get_overview() -> 'OverviewReport'`
- `get_technician_workload() -> 'list[WorkloadRow]'`
- `get_service_analysis() -> 'list[CountRow]'`
- `get_category_analysis() -> 'list[CountRow]'`
- `get_sla_violations() -> 'list[SlaViolationRow]'`

### `ServiceRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(service: 'ITService') -> 'ITService'`
- `find_by_id(id: 'int') -> 'ITService | None'`
- `find_all() -> 'list[ITService]'`
- `exists_by_name(name: 'str') -> 'bool'`

### `SettingsRepository`(ABC)  <sub>app.ports.repositories</sub>
- `get(key: 'str', default: 'str | None' = None) -> 'str | None'`
- `put(key: 'str', value: 'str') -> 'None'`

### `SlaEventRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(event: 'SlaEvent') -> 'SlaEvent'`
- `find_by_incident(incident_id: 'int') -> 'list[SlaEvent]'`
- `exists(incident_id: 'int', event_type: 'SlaEventType') -> 'bool'`

### `SlaPolicyRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(policy: 'SlaPolicy') -> 'SlaPolicy'`
- `find_by_id(id: 'int') -> 'SlaPolicy | None'`
- `find_default() -> 'SlaPolicy | None'`
- `find_all() -> 'list[SlaPolicy]'`

### `UserRepository`(ABC)  <sub>app.ports.repositories</sub>
- `save(user: 'User') -> 'User'`
- `find_by_id(id: 'int') -> 'User | None'`
- `find_by_username(username: 'str') -> 'User | None'`
- `find_all() -> 'list[User]'`
- `find_by_role(role: 'Role') -> 'list[User]'`
- `find_admins_by_level(level: 'AdminLevel') -> 'list[User]'`

## Ports: service interfaces  <sub>app/ports/services.py</sub>

### `AuthService`(ABC)  <sub>app.ports.services</sub>
- `login(username: 'str', password: 'str') -> 'User'`
- `register_employee(request: 'RegisterRequest') -> 'User'`
- `get_user(user_id: 'int') -> 'User | None'`

### `IncidentService`(ABC)  <sub>app.ports.services</sub>
- `create_incident(actor: 'User', request: 'CreateIncidentRequest') -> 'Incident'`
- `get_incident(actor: 'User', incident_id: 'int') -> 'Incident'`
- `search(actor: 'User', criteria: 'IncidentSearchCriteria') -> 'list[Incident]'`
- `assign(actor: 'User', incident_id: 'int', technician_id: 'int') -> 'Incident'`
- `auto_assign(actor: 'User', incident_id: 'int') -> 'Incident'`
- `recommend_technicians(actor: 'User', incident_id: 'int') -> 'list[RankedTechnician]'`
- `acknowledge(actor: 'User', incident_id: 'int') -> 'Incident'`
- `start_investigation(actor: 'User', incident_id: 'int') -> 'Incident'`
- `add_note(actor: 'User', incident_id: 'int', text: 'str') -> 'Incident'`
- `request_info(actor: 'User', incident_id: 'int', question: 'str') -> 'Incident'`
- `respond_to_info_request(actor: 'User', incident_id: 'int', answer: 'str') -> 'Incident'`
- `resolve(actor: 'User', incident_id: 'int', summary: 'str', details: 'str') -> 'Incident'`
- `verify(actor: 'User', incident_id: 'int') -> 'Incident'`
- `reject_resolution(actor: 'User', incident_id: 'int', reason: 'str') -> 'Incident'`
- `close(actor: 'User', incident_id: 'int') -> 'Incident'`
- `submit_feedback(actor: 'User', incident_id: 'int', rating: 'int', comment: 'str') -> 'Incident'`
- `override_priority(actor: 'User', incident_id: 'int', priority: 'Priority', reason: 'str') -> 'Incident'`
- `get_audit_trail(actor: 'User', incident_id: 'int') -> 'list[AuditRecord]'`

### `LookupService`(ABC)  <sub>app.ports.services</sub>
- `list_active_services(actor: 'User') -> 'list[ITService]'`
- `list_active_categories(actor: 'User') -> 'list[Category]'`
- `list_technicians(actor: 'User') -> 'list[Technician]'`

### `AdminService`(ABC)  <sub>app.ports.services</sub>
- `list_users(actor: 'User') -> 'list[User]'`
- `create_user(actor: 'User', request: 'CreateUserRequest') -> 'User'`
- `deactivate_user(actor: 'User', user_id: 'int') -> 'User'`
- `activate_user(actor: 'User', user_id: 'int') -> 'User'`
- `set_technician_availability(actor: 'User', user_id: 'int', available: 'bool') -> 'User'`
- `list_services(actor: 'User') -> 'list[ITService]'`
- `create_service(actor: 'User', request: 'ServiceRequest') -> 'ITService'`
- `update_service(actor: 'User', id: 'int', request: 'ServiceRequest') -> 'ITService'`
- `list_categories(actor: 'User') -> 'list[Category]'`
- `create_category(actor: 'User', request: 'CategoryRequest') -> 'Category'`
- `update_category(actor: 'User', id: 'int', request: 'CategoryRequest') -> 'Category'`
- `list_sla_policies(actor: 'User') -> 'list[SlaPolicy]'`
- `save_sla_policy(actor: 'User', request: 'SlaPolicyRequest') -> 'SlaPolicy'`
- `list_assignment_strategies(actor: 'User') -> 'list[str]'`
- `get_assignment_strategy(actor: 'User') -> 'str'`
- `set_assignment_strategy(actor: 'User', name: 'str') -> 'None'`
- `list_priority_strategies(actor: 'User') -> 'list[str]'`
- `get_priority_strategy(actor: 'User') -> 'str'`
- `set_priority_strategy(actor: 'User', name: 'str') -> 'None'`
- `is_time_simulated(actor: 'User') -> 'bool'`
- `get_current_time(actor: 'User') -> 'datetime'`
- `advance_time(actor: 'User', minutes: 'int') -> 'datetime'`
- `reset_time(actor: 'User') -> 'datetime'`
- `run_sla_check_now(actor: 'User') -> 'int'`
- `run_escalation_check_now(actor: 'User') -> 'int'`

### `ReportService`(ABC)  <sub>app.ports.services</sub>
- `overview(actor: 'User') -> 'OverviewReport'`
- `technician_workload(actor: 'User') -> 'list[WorkloadRow]'`
- `service_analysis(actor: 'User') -> 'list[CountRow]'`
- `category_analysis(actor: 'User') -> 'list[CountRow]'`
- `sla_violations(actor: 'User') -> 'list[SlaViolationRow]'`
- `audit_log(actor: 'User', audit_filter: 'AuditFilter') -> 'list[AuditRecord]'`
- `correlation_groups(actor: 'User') -> 'list[CorrelationGroup]'`

### `NotificationService`(ABC)  <sub>app.ports.services</sub>
- `list_for_user(actor: 'User', limit: 'int') -> 'list[Notification]'`
- `unread_count(actor: 'User') -> 'int'`
- `mark_read(actor: 'User', notification_id: 'int') -> 'None'`
- `mark_all_read(actor: 'User') -> 'None'`

## Container  <sub>app/ports/container.py</sub>
`Container(auth, incidents, lookup, admin, reports, notifications)` (all optional, default None).
P3: `build_real_container(settings)` in `app/services/wiring.py`. P4: `build_stub_container()` in `app/web/stubs/wiring.py`. `app/main.py` picks one from `ITSM_MODE` and stores it as `app.state.container`.
