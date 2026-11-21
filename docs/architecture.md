# System architecture

I-ITSM is a layered Python application. Each layer talks only to the one beneath it through an
interface, so any layer can be tested or replaced on its own. The layering is enforced by an
automated test (`tests/test_architecture.py`) that scans every import.

## 1. The layers

```
  Browser (Employee / Technician / Administrator)
        |  HTML pages and form posts
        v
+------------------------------+
| web/            (P4)         |  routes, templates, login session, error pages
+--------------+---------------+
               | calls service methods (interfaces in ports/services.py)
               v
+------------------------------+        +--------------------------------+
| services/       (P3)         | -----> | domain/          (P1)          |
| workflow, security, audit,   |  uses  | Incident + 8 state classes,    |
| notifications, jobs          |        | strategies, SLA engine, duplicate|
+--------------+---------------+        | and escalation logic            |
               | calls repository methods +--------------------------------+
               | (interfaces in ports/repositories.py)        ^
               v                                              | builds and reads
+------------------------------+                              | domain objects
| persistence/    (P2)         | -----------------------------+
| SQL, repositories, seed data |
+--------------+---------------+
               v
          SQLite file          <--- background scheduler (SLA + escalation checks)
                                    runs inside the app and uses the same services layer
```

| Layer | Folder | Owner | May import |
| --- | --- | --- | --- |
| Domain | `app/domain/` | P1 | Python standard library only |
| Contract | `app/ports/` | shared, frozen | domain |
| Persistence | `app/persistence/` | P2 | domain, ports |
| Services | `app/services/` | P3 | domain, ports (and `persistence` only in `wiring.py`) |
| Web | `app/web/` | P4 | ports, and enums / exceptions / read-only entities from domain |

The `ports/` folder holds only abstract classes and plain data carriers: the repository
interfaces, the six service interfaces, the request/report data classes and the `Container`. It
is the seam between layers, which is why the web layer can be built against stand-ins and the
services against in-memory fakes.

## 2. The services layer (this document's focus)

```
app/services/
  security/   password_hasher  input_rules  access_policy
  impl/       auth_service  incident_service  admin_service  lookup_service
              report_service  notification_service  user_factory  strategy_registry
  observers/  audit_observer  notification_observer  observer_registrar
  channels/   notification_channel  in_app_channel  simulated_email_channel
  jobs/       sla_monitor_job  escalation_job  scheduler
  wiring.py   the composition root
```

- **Services orchestrate; the domain decides.** `IncidentServiceImpl` loads an incident, attaches
  observers, checks the actor may see it, calls one domain method (for example
  `incident.acknowledge(...)`), and saves. Whether that action is legal in the current status is
  decided by the incident's state objects, never by an `if status == ...` in a service.
- **Every service method checks the actor itself.** Authorization is not left to the web layer.
  It is checked in the service (`AccessPolicy`) and again inside the domain (`permissions.py`).
- **Time is injected.** Nothing reads the clock directly. A `TimeProvider` is passed in, which is
  what lets the demo fast-forward the clock and lets tests control it.

### Design patterns used in this layer

| Pattern | Where | What problem it solves |
| --- | --- | --- |
| **Observer** | `AuditObserver`, `NotificationObserver` listen to the incident's events | Writing audit records and sending notifications without the incident knowing who listens |
| **Strategy** | Priority and assignment strategies behind `StrategyRegistry`; `NotificationChannel` implementations | Swapping an algorithm or a delivery mechanism at run time, with no change to callers |
| **Factory** | `UserFactory.create` | One place decides whether to build an Employee, Technician or Administrator |
| **Repository** | Every service talks to repository interfaces | No SQL outside `persistence/` |
| **Adapter (flavour)** | `NotificationChannel` | A real email or SMS gateway would be wrapped in one more class |
| **State** (domain, used here) | `Incident` | Illegal transitions such as NEW to CLOSED are impossible by construction |

## 3. One request through the layers: reporting an incident

`IncidentServiceImpl.create_incident`:

1. Check the actor is a signed-in, active user and validate the request (blank text, length
   limits, number of affected users, impact and urgency).
2. Load the service and the category (missing or inactive: `ServiceNotFoundError`,
   `CategoryNotFoundError`).
3. Reject an exact resubmission: same reporter, same title and service within 10 minutes.
4. Build the `Incident` with the domain constructor.
5. **Calculate the priority** with the active strategy and **build the SLA tracker** from the
   service's own policy, else the default policy (`MissingSlaConfigurationError` if neither).
   Both are pure calculations done *before* anything is saved, so a configuration error leaves
   no half-created incident behind.
6. **Save once**, so the incident gets its id and ticket number (INC-1001, ...).
7. Attach the observers and call `record_creation`: the audit observer writes a record and the
   notification observer tells the reporter and the administrators.
8. Compare with open incidents on the same service from the last 24 hours; flag a possible
   duplicate (never merge or reject).
9. `classify` (system actor): stores priority and SLA tracker, status becomes CLASSIFIED. Save.
10. Auto-assign: the active strategy chooses a technician (skill-based falls back to load-based
    if nobody with the skill is free). If nobody at all qualifies, the incident simply stays
    CLASSIFIED. Otherwise `assign_to`, which notifies the technician and the reporter. Save.
11. Return the incident.

Every other action (acknowledge, resolve, verify, close, ...) follows one short pattern: load,
attach observers, check access, call the domain method, save.

**Observers are never stored in the database**, so every incident that is created or loaded is
given its observers again through `ObserverRegistrar.attach`. Forgetting this would silently
lose audit records and notifications.

## 4. The composition root (`app/services/wiring.py`)

Something has to create the repositories, hand them to the services, and hand the services to the
web layer. That single place is the *composition root*. Everywhere else, a class receives what it
needs through its constructor and never creates its own helpers. (Analogy: the restaurant manager
hires the cook, gives the cook a pantry, and seats the guests.)

`assemble_container(repos, time_provider, email_log_path)` builds, in this order:

1. the strategy registries (priority: `weighted_score`, `rule_based`; assignment:
   `skill_based`, `load_based`, `weighted_recommendation`), whose active choice is read from the
   settings table on every use;
2. the notification channels (in-app and simulated email);
3. the observers and the registrar;
4. the SLA monitor job and the escalation job;
5. the six services, each given only what it needs, and the scheduler.

It touches no database and starts no thread, so the same function builds a container over the real
SQLite repositories or the in-memory fakes used by the tests.

`build_real_container(settings)` then adds the real parts:

1. open the database and create the tables (`Database.initialise`);
2. create the SQLite repositories and the clock (simulated if `SIMULATED_TIME`, else real);
3. `assemble_container(...)`;
4. if `SEED_DEMO_DATA`, run the demo data seeder (it does nothing on a database that already has
   users);
5. if `ENABLE_SCHEDULER`, start the background scheduler. This is done last so the jobs never see
   half-seeded data.

`app/main.py` chooses between `build_real_container` and the web layer's stub container using the
`ITSM_MODE` setting (`real` by default, or `stub`), and stores the result as
`app.state.container`. Every web route reads its services from there and never knows which mode
it runs in, which is why the web layer could be built before the real services existed.

## 5. Background jobs

A `BackgroundScheduler` (APScheduler) runs two jobs every 30 seconds inside the application:

- **SLA monitor.** For every open incident it asks the domain's SLA calculator what is new. A
  warning (at 80 percent of a deadline) or a violation is recorded **once only**: the tracker's
  flags and a unique rule in the `sla_events` table both prevent repeats. Status-only changes,
  such as an incident resolved in time becoming MET, are saved quietly.
- **Escalation.** A P1 that is still ASSIGNED after its response deadline moves to TEAM_LEAD, then
  one level higher every 10 minutes, up to IT_MANAGER.

Each job handles one incident at a time inside its own error handling, so one bad incident never
stops the others. The two jobs can also be run on demand from the administrator pages
(`run_sla_check_now`, `run_escalation_check_now`), and the demo clock can be advanced, which is how
the demo triggers an escalation within seconds.

## 6. How the system evolves with many more users

| Pressure | Change | Why it is cheap here |
| --- | --- | --- |
| Slow lookups (services, categories, technicians) | Put a cache in front of the lookup service | The web layer only sees `LookupService` |
| Notifications and SLA checks slow the request | Move them onto a message queue with worker processes instead of running in-process | Observers and jobs already sit behind small interfaces; a queue-backed channel is one more `NotificationChannel` class |
| One SQLite writer becomes the bottleneck | Replace SQLite with PostgreSQL | Only `app/persistence/` changes (see `docs/database_design.md`) |
| One application server is not enough | Run several servers behind a load balancer and move sessions to a shared store; run the scheduler in exactly one of them | Services hold no per-user state; the scheduler is already a separate object |
| Teams grow | Split services (incidents, notifications, reporting) into separate deployable services | The ports already define the boundaries |

## 7. Known limitations of this architecture

- Observers fire when the domain method completes, *before* the incident is saved. If the save then
  fails, an audit record can exist for a change that was not stored.
- A job (or a user) loads an incident, changes it and saves the whole row, and the contract has no
  version check. If two of them act on the same incident within a few milliseconds, the later save
  wins.
- The scheduler lives inside the web process. With several processes, each would run its own
  scheduler (the once-only rules make this safe but wasteful).
- The text diagram above is also available as a rendered picture, `docs/report/diagrams/architecture.png`.

## 8. The web layer (`app/web/`)

The web layer is a set of server-rendered pages. It talks only to the six service interfaces, reached through
`request.app.state.container`, and never imports `services` or `persistence` (the architecture test enforces
this; from the domain it may use only enums, exceptions and the read-only entity classes).

```
app/web/
  setup.py              install_web(app): mounts the static files, adds every router, installs the error handlers
  security.py           who is signed in (from the session) and the role guards
  errors.py             one place that turns exceptions into pages, messages and redirects
  templating.py         render(): adds the user, role menu, unread count and flash messages to every page
  template_helpers.py   date and duration formats, badge colours, the menus, flash messages
  forms.py              turns submitted form text into numbers, dates and enum values
  actions.py            which buttons an incident page shows for a role and status (a display hint only)
  routes/               auth, common, employee, technician and admin routers, split by role
  templates/            base layout, shared macros, and one folder per area
  static/               the small stylesheet
  stubs/                stub mode: the six services backed by in-memory sample data
```

**One request.** The browser sends a page request or a form post. The router's *guard dependency* reloads the
signed-in user through the auth service and checks the role (anonymous: redirect to `/login`; wrong role: 403).
The route function then reads the form, calls **one** service method, and either renders a template or
**redirects** (post, then redirect, then get, so refreshing never resubmits). Messages for the next page are
kept in the session as flash messages and shown once. If the service raises an exception, `errors.py` decides
what the user sees (`docs/exceptions.md`).

**Rules the web layer follows.** Routes contain no business rules: whether an action is legal, who may do it,
and what a priority is are all decided below. The signed-in user always comes from the session, never from a
form field. Which buttons appear is decided in `actions.py`, but that is only a hint; the service and the
domain still enforce everything.

**Role-based pages.** Three sets of pages and menus (employee, technician, administrator) are built from
separate templates and routers. `docs/use_case_diagram.md` lists them against the use cases.

**Real mode and stub mode.** `app/main.py` builds a container for `ITSM_MODE=real` (the real services,
`app/services/wiring.py`) or `ITSM_MODE=stub` (`app/web/stubs/wiring.py`). The pages cannot tell the
difference. The stub services keep sample data in memory and apply the domain's own incident methods, so
illegal transitions and permission errors behave as they do in real mode, which makes stub mode useful for
working on the pages without a database. Web tests use the real services over in-memory repositories.

**Limitations specific to this layer.** Pages are server-rendered, so there is no live update: a new
notification appears on the next page load. Bootstrap is loaded from a CDN, so the pages need internet access.
