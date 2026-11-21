# Technology selection report

The brief is technology-independent and asks every team to justify its choices. This report answers its
nine questions. Library versions are the ones pinned in `requirements.txt` and used for the tests.

## 1. The stack at a glance

| Need | Choice | Version |
| --- | --- | --- |
| Language | **Python** | 3.11 or newer (developed and tested on 3.12.10) |
| Web framework | **FastAPI**, which builds on **Starlette** | 0.162.7 |
| Application server | **Uvicorn** | 0.54.0 |
| Pages | **Jinja2** templates, server rendered | 3.1.6 |
| Page styling | **Bootstrap 5**, loaded from a CDN link (no build step) | 5.3.3 |
| Form handling | **python-multipart** | 0.0.33 |
| Login session | Starlette `SessionMiddleware` (signed cookie), signing by **itsdangerous** | 2.2.0 |
| Password hashing | **bcrypt** | 5.0.0 |
| Database | **SQLite**, through Python's built-in `sqlite3`, plain SQL | bundled with Python |
| Background jobs | **APScheduler** (`BackgroundScheduler`) | 3.11.3 |
| Tests | **pytest** and FastAPI's `TestClient` (needs **httpx**) | 9.2.0 and 0.28.1 |
| Code checking | **ruff** | 0.17.5 |
| Diagrams | Graphviz (class diagrams), PlantUML (use cases), dbdiagram.io (ER diagram) | n/a |
| Version control | Git and GitHub | n/a |

## 2. The nine questions

### 1. Why did you choose this programming language?

The team preferred Python, and the brief is language-neutral. Python's `abc.ABC`, `Enum`, properties and
dataclasses cover every OOP idea the brief asks for (section 8 below). It also reads closely to pseudo
code, which matters in a team that must be able to explain every module on camera, and AI-assisted
development produces reliable Python.

*Alternatives considered:* Java with Spring Boot (strong typing and interfaces, but a heavier setup and
more boilerplate), TypeScript (a good fit for a single-language web stack, but weaker for showing classic
OOP).

### 2. Why did you choose this frontend technology?

**Server-rendered HTML with Jinja2 templates and Bootstrap 5.** Every page is produced on the server
from a template, so there is no second project, no build tool and no JavaScript framework to learn. The
three roles get three different sets of pages and menus from separate templates. Bootstrap supplies a
responsive layout (the pages work on a phone), forms, tables and badges without custom CSS.

*Alternatives considered:* a React (or Vue/Angular) single-page application on top of a REST API. That
would give a smoother interface but doubles the work (two toolchains, an API contract to maintain) for no
gain in the marks-bearing parts of the brief.

### 3. Why did you choose this backend technology?

**FastAPI served by Uvicorn.** It is small and clear, validates input, and keeps routes short, which fits
our rule that a route only reads a form, calls one service method and redirects. It runs sync routes in a
thread pool, which suits our blocking database code.

*Alternatives considered:* Flask (also fine; less built in), Django. Django's model-centric ORM style
encourages "anaemic" domain objects with the logic elsewhere and hides the object design the project is
meant to show.

### 4. Why did you select this database?

**SQLite**, with plain SQL through the standard library. It needs no installation or server, the whole
database is one file, and tests create a throwaway one in milliseconds, so four people can run the same
project on their own laptops and a demo starts reliably. The expected volume is far below SQLite's limits.
Plain SQL keeps the domain classes free of storage code: only the repository classes know SQL.

*Alternatives considered:* PostgreSQL (the right choice for many concurrent users, but needs a server),
SQLAlchemy ORM (tempts mixing storage code into domain classes). Moving to PostgreSQL later means writing
new repository classes and a new `Database` helper; nothing else changes (`docs/database_design.md`).

### 5. Why did you choose this architecture?

A **layered architecture with an explicit contract**: web, services, domain, persistence, and a frozen
`ports/` folder of interfaces between them. The rules are enforced by an automated test that scans every
import, so the layering cannot erode unnoticed.

- It makes the system **maintainable** (business rules live in one place, with no SQL or web code mixed in).
- It makes it **extensible**: a new notification channel, assignment strategy or database is one new class.
- It let four people work in parallel without waiting for each other, because each layer was built against
  interfaces and in-memory stand-ins.
- It makes the system **testable**: the domain needs only Python, services run against in-memory fakes, and
  time is injected so tests and the demo control the clock.

*Alternatives considered:* microservices (far too heavy for this scope), a single script or "fat" routes
with logic and SQL inline (quick, but the design would not be defensible).

### 6. What alternatives did you consider?

| Need | Chosen | Considered |
| --- | --- | --- |
| Language | Python | Java with Spring Boot; TypeScript |
| Web framework | FastAPI | Flask; Django |
| Pages | Jinja2 and Bootstrap | React single-page application |
| Login session | Signed cookie session | JWT (better for mobile or public APIs; unnecessary for server-rendered pages) |
| Database | SQLite | PostgreSQL; SQLAlchemy ORM |
| Background jobs | APScheduler | Celery (needs a message broker); raw threads |
| Tests | pytest | unittest |

### 7. What are the advantages and limitations of the stack?

**Advantages**
- Fast to build and to run: one `pip install`, no database server, no build step.
- Clean layering that the team can explain and a test can verify.
- A large automated test suite runs in about a minute, including pages and a real seeded database.
- Easy to demonstrate: the demo clock and on-demand checks make deadlines and escalations visible in
  seconds.

**Limitations**
- **SQLite allows one writer at a time** and is a single file on a single machine, so it is not a choice for
  many concurrent users.
- **Server-rendered pages** reload on every action; there is no live update (a user sees a new notification
  on the next page load).
- **No CSRF tokens, no HTTPS, no rate limiting** in the demo; the full list is in `docs/security.md`.
- Bootstrap is loaded from a public CDN, so the pages need internet access and no integrity hash is
  checked.
- **The scheduler runs inside the web process**, so running several server processes would give each its
  own scheduler (safe because of the once-only rules, but wasteful).
- Python has **no `interface` keyword and no truly private fields**. We say this honestly and compensate
  (see question 8).

### 8. How does your technology support object-oriented design?

| Brief requirement | How Python and the design express it |
| --- | --- |
| Encapsulation | Fields start with `_` (private by convention) and are read through `@property` with **no setters**. State changes only through behaviour methods such as `incident.acknowledge(...)`. |
| Abstraction and interfaces | `abc.ABC` with `@abstractmethod`: `PriorityStrategy`, `AssignmentStrategy`, `NotificationChannel`, `IncidentObserver`, every repository and service interface. |
| Inheritance (real "is-a") | `User` to `Employee`, `Technician`, `Administrator`; `IncidentState` to eight state classes. |
| Polymorphism | Any `AssignmentStrategy` or `NotificationChannel` can be swapped at run time and callers do not change. |
| Composition | An `Incident` owns its SLA tracker, notes, resolution and feedback. |
| Association and aggregation | Incident and reporter, incident and service, technician and skills, service and SLA policy. |
| Exception handling | One hierarchy under `ITSMError`, caught in one place by the web layer. |
| Collections | `dict` (strategy registry, SLA targets by priority), `set` (skills), `list` (observers, notes), `defaultdict` (grouping). |
| Design patterns | **State, Strategy, Observer, Repository, Factory**, with Adapter used for notification channels. |

`docs/oop_and_patterns.md` shows where each appears in the code.

### 9. How would the system evolve if the number of users increased significantly?

See `docs/architecture.md`, section 6, for the full table. In short: a cache in front of the lookup
service; a message queue and worker processes for notifications and SLA checks; PostgreSQL in place of
SQLite (only `app/persistence/` changes); several application servers behind a load balancer with sessions
in a shared store and the scheduler running in exactly one of them; and, if the team grows, splitting
incidents, notifications and reporting into separate services along the boundaries the ports already
define.
