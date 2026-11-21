# Requirements specification

## 1. Purpose and scope

I-ITSM is a web application for an organisation's IT support desk. An employee reports a problem
(for example "the payment application is unavailable"). The system creates the incident, classifies
it, calculates its priority, finds the applicable SLA, assigns a technician, notifies the people
involved, tracks the deadlines, records every action, and finally closes the incident.
Administrators configure the system and see dashboards, search and reports.

**Lifecycle:** NEW, CLASSIFIED, ASSIGNED, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, VERIFIED, CLOSED.

**Out of scope (optional in the brief):** real email or SMS delivery, real-time push, machine
learning, cloud deployment, a JavaScript front end, a mobile app.

## 2. User roles

| Role | Can do |
| --- | --- |
| **Employee** | Register and log in; report an incident; view and track their own incidents; add information and answer the technician's questions; see the resolution; verify or reject it; close; give feedback |
| **Technician** | View assigned incidents and their own workload; acknowledge; investigate; add notes; ask the reporter for information; resolve with resolution details |
| **Administrator** | Manage users and technicians; manage IT services, categories and SLA policies; choose the assignment and priority strategies; assign and reassign; override a priority; monitor all incidents; view reports, the audit log and SLA violations; use the demo clock and run the checks on demand |
| **System** (not a person) | Automatic actions: classifying incidents, flagging duplicates, recording SLA events, escalating. Appears in the audit trail as "System". |

## 3. Functional requirements

Each requirement names where it is implemented. IDs are used by the test documents.

### Users and security
| ID | Requirement | Implemented by |
| --- | --- | --- |
| FR-1 | Three roles: Employee, Technician, Administrator | `domain/models/user.py`, `UserFactory` |
| FR-2 | Registration (always as Employee) and login with generic failure messages | `AuthServiceImpl` |
| FR-3 | Passwords stored only as bcrypt hashes; minimum length 8 | `PasswordHasher`, `input_rules` |
| FR-4 | Role-based access to every operation; employees see only their own incidents, technicians only their assigned ones | `AccessPolicy`, `domain/state/permissions.py` |
| FR-5 | Administrators create users and deactivate or reactivate them (never delete); set technician availability | `AdminServiceImpl` |

### Incidents
| ID | Requirement | Implemented by |
| --- | --- | --- |
| FR-6 | Create an incident with category, affected service, description, impact, urgency and number of affected users | `IncidentServiceImpl.create_incident` |
| FR-7 | Reject an accidental resubmission (same reporter, title and service within 10 minutes) | `IncidentServiceImpl` |
| FR-8 | Strict lifecycle: illegal transitions (for example NEW to CLOSED) are impossible | State pattern in `domain/state/` |
| FR-9 | Technician acknowledges, investigates, adds notes, requests information; reporter answers; technician resolves; reporter verifies or rejects; closure; feedback after verification | `IncidentServiceImpl`, domain state classes |
| FR-10 | View an incident and search incidents on at least five criteria: ticket number, status, priority, category, service, technician, reporter, SLA status, date range and keyword | `IncidentRepository.search`, `IncidentServiceImpl.search` |
| FR-11 | New categories and services can be added without changing unrelated code | `AdminServiceImpl` |

### Intelligence
| ID | Requirement | Implemented by |
| --- | --- | --- |
| FR-12 | Priority P1 to P4 from impact, urgency, business criticality and number of affected users; at least two swappable strategies | `WeightedScorePriorityStrategy`, `RuleBasedPriorityStrategy`, `StrategyRegistry` |
| FR-13 | At least two technician-assignment strategies, switchable at run time without restart; automatic assignment on creation; manual assignment and reassignment | `SkillBasedAssignment`, `LoadBasedAssignment`, `WeightedRecommendationStrategy`, `IncidentServiceImpl` |
| FR-14 | Smart technician recommendation with readable reasons | `WeightedRecommendationStrategy.rank`, `IncidentServiceImpl.recommend_technicians` |
| FR-15 | Possible-duplicate detection among open incidents on the same service in the last 24 hours (flag only) | `DuplicateDetector` |
| FR-16 | Automatic escalation of an unacknowledged P1: TEAM_LEAD, then SYSTEM_ADMIN, then IT_MANAGER | `EscalationPolicy`, `EscalationJob` |
| FR-17 | Correlation of related open incidents on one service (stretch) | `CorrelationDetector`, `ReportServiceImpl.correlation_groups` |

### SLA
| ID | Requirement | Implemented by |
| --- | --- | --- |
| FR-18 | Identify the applicable SLA (the service's own policy, else the default); calculate response and resolution deadlines | `SlaCalculator`, `IncidentServiceImpl` |
| FR-19 | Warn at 80 percent of a deadline and detect violations, each recorded once | `SlaMonitorJob` |
| FR-20 | Administrators configure SLA policies; there is always exactly one default | `AdminServiceImpl.save_sla_policy` |
| FR-21 | Administrator may override a priority; deadlines are recalculated | `IncidentServiceImpl.override_priority` |

### Notifications, audit and reporting
| ID | Requirement | Implemented by |
| --- | --- | --- |
| FR-22 | At least two notification mechanisms: in-app and simulated email; adding another means adding one class | `InAppChannel`, `SimulatedEmailChannel`, `NotificationChannel` |
| FR-23 | Notify the right people for each event | `NotificationObserver` (recipient table) |
| FR-24 | A complete, append-only audit trail of every action with timestamp, actor, action, previous and new status | `AuditObserver`, `AuditRepository` |
| FR-25 | Reports: overview, technician workload, incidents per service and per category, SLA violations, audit log | `ReportServiceImpl`, `ReportRepository` |
| FR-26 | Persistence of users, services, incidents, technicians, SLA policies, audit records and resolutions | `app/persistence/` (SQLite) |
| FR-27 | A demo clock that can be advanced, and on-demand SLA and escalation checks, so a demo can show breaches within seconds | `AdminServiceImpl`, `SimulatedTimeProvider` |

## 4. Non-functional requirements

| Area | Requirement |
| --- | --- |
| **Security** | Authentication, role-based authorization in every layer, bcrypt passwords, input validation, parameterised SQL. Limitations are listed honestly in `docs/security.md`. |
| **Maintainability** | Four layers with enforced import rules (`tests/test_architecture.py`); business logic only in the domain; SQL only in `persistence`; one composition root. |
| **Extensibility** | New strategy, notification channel, category, service or storage back end each require adding a class or a row, not editing unrelated code. |
| **Testability** | The domain needs nothing but Python; services run against in-memory fakes; time is injected so tests and the demo control the clock. |
| **Reliability** | Failures are isolated: a failing channel, job step or incident never stops the others; configuration errors are detected before anything is saved; background jobs record each SLA event once only. |
| **Performance** | Lists of incidents are loaded with a fixed handful of queries, not one per row. Background checks run every 30 seconds. Expected volume (hundreds to thousands of incidents) is well within SQLite. |
| **Usability** | Separate interface per role; plain-language error messages naming the field at fault. |
| **Portability** | Runs on Windows, macOS and Linux with Python 3.11 or newer; no database server to install. |

## 5. Business rules

All constants live in `BusinessRules` (`app/domain/business_rules.py`); nothing else hard-codes them.

| Rule | Value |
| --- | --- |
| Priority score | impact x urgency x business criticality, each 1 to 3, so 1 to 27 |
| Score to priority | 18 or more: P1. 9 or more: P2. 4 or more: P3. Otherwise P4. |
| Affected-users bump | 50 or more affected users raises the priority one level (P1 stays P1) |
| SLA targets (response / resolution) | P1: 5 min / 30 min. P2: 15 min / 2 h. P3: 1 h / 8 h. P4: 4 h / 24 h |
| Which SLA policy applies | The service's own policy, else the default policy, else `MissingSlaConfigurationError` |
| SLA clocks | Both start at creation. The response clock stops at acknowledgement; the resolution clock stops when the incident is RESOLVED. |
| SLA warning | At 80 percent of a deadline. Each warning or violation is recorded once only. |
| Maximum active incidents per technician | 5 (active means ASSIGNED, ACKNOWLEDGED or IN_PROGRESS) |
| Exact resubmission | Same reporter, same title and service within 10 minutes is rejected |
| Possible duplicate | Open incidents on the same service from the last 24 hours. Score = 0.7 x text similarity + 0.3 x (1 if same service). At 0.5 or more it is flagged. Flag only: never merged or rejected. |
| Correlation | 3 or more open incidents on one service created within 60 minutes: probable service-level problem |
| Escalation | A P1 still ASSIGNED after its response deadline goes to TEAM_LEAD, then one level higher every 10 minutes, up to IT_MANAGER |
| Recommendation weights | Skill match 40, low current load 30, experience 15, past work on this service 15 |
| Scheduler interval | SLA and escalation checks every 30 seconds |
| Password | At least 8 characters (at most 72 bytes), stored as a bcrypt hash |
| Demo password | `Password@123` for every seeded user |

## 6. Lifecycle rules

| From status | Allowed action, next status | Who may do it |
| --- | --- | --- |
| NEW | classify, CLASSIFIED | System |
| CLASSIFIED | assign, ASSIGNED | System or an administrator |
| ASSIGNED | acknowledge, ACKNOWLEDGED | The assigned technician |
| ASSIGNED | reassign, ASSIGNED | An administrator |
| ACKNOWLEDGED | start investigation, IN_PROGRESS | The assigned technician |
| IN_PROGRESS | request information (stays) | The assigned technician |
| IN_PROGRESS | respond to information request (stays) | The reporter |
| IN_PROGRESS | resolve, RESOLVED | The assigned technician |
| RESOLVED | verify, VERIFIED | The reporter or an administrator |
| RESOLVED | reject resolution, IN_PROGRESS | The reporter |
| VERIFIED | close, CLOSED | The reporter or an administrator |
| VERIFIED or CLOSED | submit feedback | The reporter |
| Any status except CLOSED | add note | The assigned technician (investigation) or the reporter (additional information) |
| Any status except CLOSED | escalate, change priority, flag possible duplicate, apply SLA result | System or an administrator |
| CLOSED | nothing | No one |
