"""Builds docs/report/I-ITSM_Project_Report.docx from the project documents, diagrams and screenshots.

Run from the repository root (Windows):
    .venv\\Scripts\\python.exe docs\\report\\tools\\build_report.py
Then export_pdf.ps1 updates the table of contents and saves the PDF.

The text of most chapters is taken from the Markdown files in docs/, so the report and the repository never
disagree. Everything written only for the report (introduction, captions, conclusion) is in this file.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from docx_writer import Docx, inline, para, parse_markdown, run  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
DIAGRAMS = DOCS / "report" / "diagrams"
SHOTS = DOCS / "screenshots"
OUT = DOCS / "report" / "I-ITSM_Project_Report.docx"
REPO_URL = "https://github.com/Chesan1203/iitsm"

doc = Docx("I-ITSM: Intelligent IT Service Management and Incident Resolution - Project report",
           "Group 6 | I-ITSM project report")

GROUP = "Group 6"
TEAM = [("N B Chesan", "2024B3AD0535H"),
        ("Sakthi Aadhithya Babu", "2024B3AD0586H"),
        ("V Anush", "2024B3A70688H"),
        ("Sugapriyan S", "2024B5A70843H")]


# ----------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------
def strip_number(title: str) -> str:
    return re.sub(r"^\d+\.\s+", "", title)


def add_md(name: str, *, shift: int = 0, h2=None, replacements=(), drop_para=(), drop_code=(), intro=True,
           before_first_h2=None, keep_h3_numbers=False, widths=None) -> list:
    """Adds a Markdown file. shift=0: its H2 become numbered sections; shift=1: its H2 become plain sub-headings."""
    text = (DOCS / name).read_text(encoding="utf-8")
    for old, new in replacements:
        text = text.replace(old, new)
    include, seen_h2, tables = intro, False, []
    for block in parse_markdown(text):
        kind = block[0]
        if kind == "h":
            level, title = block[1], block[2]
            if level == 1:
                continue
            if level == 2:
                if not seen_h2 and before_first_h2:
                    before_first_h2()
                seen_h2 = True
                include = h2(title) if h2 else True
                if include:
                    clean = strip_number(title).replace("`", "")
                    doc.section(clean) if shift == 0 else doc.heading_plain(clean, 3)
                continue
            if include:
                clean = (title if keep_h3_numbers else strip_number(title)).replace("`", "")
                doc.heading_plain(clean, 3 + shift)
            continue
        if not include:
            continue
        if kind == "p":
            if not any(s in block[1] for s in drop_para):
                doc.text(block[1])
        elif kind == "list":
            if block[1]:
                doc.numbered(block[2], block[3])
            else:
                doc.bullet_items(block[2])
        elif kind == "table":
            doc.table(block[1], block[2], widths=widths)
            tables.append(block)
        elif kind == "code":
            if not any(s in block[1] for s in drop_code):
                doc.code(block[1])
    if not seen_h2 and before_first_h2:
        before_first_h2()
    return tables


def fig(name: str, caption: str, **kw):
    doc.figure(DIAGRAMS / name, caption, **kw)


def shot(name: str, caption: str):
    doc.figure(SHOTS / f"{name}.png", caption, max_height_in=7.6)


def count_lines(pattern: str, base: pathlib.Path) -> int:
    return sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in base.rglob(pattern))


app_files = len(list((ROOT / "app").rglob("*.py")))
app_lines = count_lines("*.py", ROOT / "app")
test_lines = count_lines("*.py", ROOT / "tests")
template_lines = count_lines("*.html", ROOT / "app" / "web" / "templates")

# ----------------------------------------------------------------------------------------------------------
# cover page and contents
# ----------------------------------------------------------------------------------------------------------
doc.cover("Intelligent IT Service Management and Incident Resolution", "I-ITSM", "Project report",
          "Object-Oriented Programming (CS F213 / MAC F212)", "Team project, submitted 22 November 2026",
          TEAM, REPO_URL, group=GROUP)
doc.contents()

# ----------------------------------------------------------------------------------------------------------
# 1 Introduction
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Introduction and team")
doc.section("Overview")
doc.text("I-ITSM (Intelligent IT Service Management and Incident Resolution) is a web application that helps the IT "
         "department of an organisation receive, prioritise, assign, track and resolve incidents. An incident is a "
         "problem that an employee reports with an IT service such as e-mail, the VPN or a payment system.")
doc.text("An employee reports an incident through a form. The system then does the routine work by itself: it calculates "
         "the priority, sets the service level agreement (SLA) deadlines, chooses a suitable technician, flags a "
         "possible duplicate, notifies the people involved and writes an audit trail. A background scheduler watches the "
         "deadlines every 30 seconds, warns before a deadline is missed, records violations, and escalates a critical "
         "incident that nobody has acknowledged up the management chain.")
doc.section("Objectives")
doc.bullets([
    "A clear object-oriented domain model: an Incident that changes state through State classes, strategies that can be "
    "swapped at run time, and observers that react to events (chapters 5 and 6).",
    "A layered architecture whose rules are enforced by an automated test, so each layer can be tested on its own (chapter 4).",
    "Three complete workflows that can be shown from start to finish (chapter 12).",
    "Intelligent features: priority scoring, technician recommendation, duplicate detection, incident correlation and "
    "automatic escalation (chapter 6).",
    "Persistence, security, documentation and a large automated test suite (chapters 8, 9 and 10).",
])
doc.section("The project in numbers")
doc.table(["Measure", "Value"], [
    ["Python source files in `app/`", f"{app_files}"],
    ["Lines of application code (Python)", f"about {app_lines:,}"],
    ["Lines of test code (Python)", f"about {test_lines:,}"],
    ["Lines of page templates (HTML)", f"about {template_lines:,}"],
    ["Automated tests", "815, all passing (domain 164, persistence 98, services 266, web 269, project-level 18)"],
    ["Database", "12 tables and 10 indexes in one SQLite file"],
    ["Web operations (routes)", "56, each with a documented access rule"],
    ["User roles", "3 (employee, technician, administrator) plus the scheduler acting as the system"],
    ["Incident lifecycle", "8 statuses, each a State class"],
    ["Strategies", "2 priority strategies and 3 assignment strategies, switchable by the administrator without a restart"],
], widths=[0.42, 0.58])
doc.section("Team and responsibilities")
doc.text(f"**{GROUP}:** " + "; ".join(f"{name} ({sid})" for name, sid in TEAM) + ".")
doc.text("The work was split into four parts with clear owners. Every part has its own documents and tests, and every "
         "member can explain how the parts fit together.")
doc.table(["Part", "Member", "Responsibility", "Main folders and documents"], [
    ["P1", "N B Chesan (2024B3AD0535H)",
     "Domain model and object-oriented design: Incident, the eight State classes, observers and events, priority and "
     "assignment strategies, the SLA engine, duplicate and correlation detection, the escalation policy",
     "`app/domain/`, `tests/domain/`, `docs/DOMAIN_README.md`, `docs/business_rules.md`, `docs/oop_and_patterns.md`, class diagrams"],
    ["P2", "Sakthi Aadhithya Babu (2024B3AD0586H)",
     "Database and persistence: the SQL schema, the ten SQLite repositories, search and report queries, the demo "
     "data seeder",
     "`app/persistence/`, `tests/persistence/`, `docs/database_design.md`, `docs/tests_p2.md`, `docs/demo_data.md`"],
    ["P3", "V Anush (2024B3A70688H)",
     "Services layer: authentication, the incident workflow, administration, reports, notifications, observers, "
     "channels, background jobs, security rules and the composition root",
     "`app/services/`, `tests/services/`, `docs/architecture.md`, `docs/security.md`, `docs/exceptions.md`, "
     "`docs/requirements.md`, `docs/tests_p3.md`"],
    ["P4", "Sugapriyan S (2024B5A70843H)",
     "Web interface: pages for the three roles, forms, error pages, stub mode, the problem analysis, the technology "
     "report and the demonstration script",
     "`app/web/`, `tests/web/`, `docs/problem_analysis.md`, `docs/technology_report.md`, `docs/demo_script.md`, "
     "`docs/tests_p4.md`"],
], widths=[0.06, 0.17, 0.4, 0.37])
doc.section("How this report covers the deliverables")
doc.table(["Deliverable in the brief", "Where in this report"], [
    ["1. Problem analysis (problem, stakeholders, challenges, solution, assumptions)", "Chapter 2"],
    ["2. Requirements specification (functional, non-functional, roles, business rules)", "Chapter 3, and section 6.4 for the algorithms"],
    ["3. System architecture diagram", "Chapter 4"],
    ["4. UML diagrams (use case and class diagrams)", "Chapter 5 (also the state and sequence diagrams)"],
    ["5. Technology stack", "Chapter 7"],
    ["6. Source code in a version-control repository", f"Chapter 13 and {REPO_URL}"],
    ["7. Database design (ER diagram, schema, relationships, sample data)", "Chapter 8"],
    ["8. Testing (at least 15 documented test cases in six categories)", "Chapter 10"],
    ["9. Project demonstration (three complete workflows)", "Chapters 11 and 12"],
    ["Team and responsibilities", "Section 1.4"],
], widths=[0.62, 0.38])

# ----------------------------------------------------------------------------------------------------------
# 2 Problem analysis, 3 Requirements
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Problem analysis")
add_md("problem_analysis.md")

doc.chapter("Requirements specification")
add_md("requirements.md")

# ----------------------------------------------------------------------------------------------------------
# 4 Architecture
# ----------------------------------------------------------------------------------------------------------
doc.chapter("System architecture")


def architecture_figure():
    fig("architecture.png", "System architecture: the five layers, what each may depend on, and where data are stored. "
                            "Arrows show the direction of dependency.", max_height_in=8.2)


add_md("architecture.md",
       h2=lambda t: not t.startswith(("6.", "7.")),
       before_first_h2=architecture_figure,
       replacements=[("The services layer (this document's focus)", "The services layer")],
       drop_code=["Browser (Employee / Technician / Administrator)"])

# ----------------------------------------------------------------------------------------------------------
# 5 UML diagrams
# ----------------------------------------------------------------------------------------------------------
doc.chapter("UML diagrams")
doc.text("This chapter contains the two diagrams required by the brief, the use case diagram and the class diagrams, and "
         "two more that explain behaviour: the incident state diagram and the sequence diagrams of the two main "
         "automatic flows.")
doc.section("Use case diagram")
fig("usecase.png", "Use case diagram: three human actors, the scheduler, the use cases of each, and the work the system does "
                   "automatically («include» and «extend»).", max_height_in=8.4)
add_md("use_case_diagram.md", shift=1, drop_para=["The rendered diagram used in the report"])

doc.new_section("landscape")
doc.section("Class diagrams")
doc.text("The domain layer is shown in five diagrams, each covering one theme. Attributes and methods are listed for the "
         "important classes, interfaces are marked, inheritance is drawn with hollow arrows, and composition and "
         "association carry their multiplicities. The diagrams were generated from the code structure by "
         "`scripts/generate_class_diagrams.py`, with the PlantUML source in `docs/class_diagram.puml`.")
for name, caption in [
    ("class_diagram_1_entities.png", "Users and reference data (`app/domain/models`)."),
    ("class_diagram_2_incident.png", "The Incident and the objects it owns (`app/domain/models`)."),
    ("class_diagram_3_lifecycle.png", "Incident lifecycle: the State pattern and the Observer pattern (`app/domain/state`, `observer`, `events`)."),
    ("class_diagram_4_strategies.png", "Strategy pattern: priority and technician assignment (`app/domain/strategies`)."),
    ("class_diagram_5_engines.png", "SLA engine, intelligent features and time (`app/domain/sla`, `intelligence`, `time_provider`)."),
]:
    doc.figure(DOCS / name, caption, max_height_in=4.7)

doc.new_section("portrait")
doc.section("Incident state diagram")
doc.text("An incident moves through eight statuses. Each status is a class (the State pattern), so an illegal move such as "
         "NEW to CLOSED simply does not exist: the base class makes every action illegal and each state overrides only "
         "what is legal there. Every action is also checked for who may perform it. Adding a note, escalating a P1, "
         "changing the priority, flagging a possible duplicate and reassigning do not change the status.")
fig("state.png", "Incident lifecycle: the eight statuses and the action, with who may perform it, that moves an incident "
                 "from one to the next.")
doc.section("Sequence diagrams")
doc.text("The first diagram follows one request through the layers when an employee reports an incident. It is the "
         "most important flow in the system: a single form submission produces a priority, SLA deadlines, a possible "
         "duplicate flag, an assigned technician, audit records and notifications.")
fig("sequence_report.png", "Sequence diagram: an employee reports an incident.", max_height_in=8.6)
doc.text("The second diagram shows the two background jobs that the scheduler runs every 30 seconds. Warnings, violations "
         "and escalations are recorded once only, and a failure on one incident never stops the others.")
fig("sequence_jobs.png", "Sequence diagram: the SLA monitor and the escalation job.", max_height_in=8.6)

# ----------------------------------------------------------------------------------------------------------
# 6 Object-oriented design
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Object-oriented design and business rules")
doc.section("OOP concepts and design patterns")
add_md("oop_and_patterns.md", shift=1)
doc.section("Domain decisions")
add_md("domain_decisions.md", shift=1)
doc.section("The domain classes at a glance")
add_md("DOMAIN_README.md", shift=1, h2=lambda t: not t.startswith("Debugging"))
doc.section("Business rules and algorithms")
add_md("business_rules.md", shift=1)

# ----------------------------------------------------------------------------------------------------------
# 7 Technology, 8 Database
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Technology stack")
add_md("technology_report.md", keep_h3_numbers=True,
       replacements=[("Graphviz (class diagrams), PlantUML (use cases), dbdiagram.io (ER diagram)",
                      "Graphviz (class diagrams), hand-drawn SVG and Mermaid rendered with Microsoft Edge (the other diagrams)")])

doc.chapter("Database design")
schema = (ROOT / "app" / "persistence" / "schema.sql").read_text(encoding="utf-8")


def database_figures():
    doc.section("Entity-relationship diagram")
    doc.text("The diagram shows every table with its key columns and the relationships between them. Foreign keys are marked FK, "
             "primary keys PK and unique columns UK. A circle on a line means \"optional\" and a crow's foot means \"many\". "
             "The `incidents` table has 36 columns; the diagram lists the main ones. The complete column list is the SQL schema "
             "in section 8.2.")
    fig("er.png", "Entity-relationship diagram of the 12 tables.", max_height_in=8.0)
    doc.section("The SQL schema")
    doc.text("`app/persistence/schema.sql` is the authoritative definition of the database. It is run at every start and "
             "every statement is `IF NOT EXISTS`, so running it again is harmless.")
    doc.code(schema.strip("\n"))


add_md("database_design.md", h2=lambda t: not t.startswith(("1.", "9.", "10.")), before_first_h2=database_figures)

# ----------------------------------------------------------------------------------------------------------
# 9 Security and exceptions
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Security and exception handling")
doc.section("Security")
add_md("security.md", shift=1)
doc.section("Exception handling")
add_md("exceptions.md", shift=1)

# ----------------------------------------------------------------------------------------------------------
# 10 Testing (landscape)
# ----------------------------------------------------------------------------------------------------------
doc.new_section("landscape")
doc.chapter("Testing")
doc.section("Approach and results")
doc.text("The project has **815 automated tests**, run with `pytest`; all of them pass. They are written at four levels, "
         "so that a failure points at the layer that caused it.")
doc.table(["Area", "Tests", "What they check"], [
    ["Domain (`tests/domain`)", "164", "State transitions, permissions, strategies, the SLA engine, duplicate and correlation "
                                         "detection and escalation, with guard tests that the domain imports only the standard "
                                         "library and never reads the clock"],
    ["Persistence (`tests/persistence`)", "98", "Every repository against a real SQLite database, constraints, search, reports "
                                                  "and the seeder"],
    ["Services (`tests/services`)", "266", "The workflow, access rules, observers, notification channels, background jobs and the "
                                            "composition root, plus complete workflows on a seeded SQLite database"],
    ["Web (`tests/web`)", "269", "Every page and action through the real application with sign-in, role guards, forms, error pages, "
                                  "stub mode, and a sweep that every route has an access rule"],
    ["Project level", "18", "Architecture rules (every import is scanned), application start-up and other checks"],
], widths=[0.22, 0.07, 0.71])
def case_count(name: str) -> int:
    first = next(b for b in parse_markdown((DOCS / name).read_text(encoding="utf-8")) if b[0] == "table")
    return len(first[2])


n_cases = case_count("tests_p2.md") + case_count("tests_p3.md") + case_count("tests_p4.md")
doc.text(f"The brief asks for at least 15 documented test cases. The tables below document **{n_cases} cases** (each one backed by "
         "one or more automated tests), spread over the six required categories: normal operation, boundary conditions, "
         "invalid input, exceptions, authorization and business rules. Each row gives the input or steps, the expected result, "
         "the actual result and whether it passed.")
doc.text("Techniques used to keep the tests meaningful: the web tests run the **real services over in-memory repositories**, "
         "a parity test keeps those fakes honest against SQLite, and **mutation testing** was used on the important rules "
         "(a rule was deliberately broken and a test had to fail). The run for this report: **815 passed**.")
doc.section("Test cases: database and persistence")
t2 = add_md("tests_p2.md", shift=1)
doc.section("Test cases: services, security, notifications and background jobs")
t3 = add_md("tests_p3.md", shift=1)
doc.section("Test cases: web layer")
t4 = add_md("tests_p4.md", shift=1)
documented = sum(len(t[2]) for tables in (t2[:1], t3[:1], t4[:1]) for t in tables)
print("documented test cases in the three tables:", documented)

doc.new_section("portrait")

# ----------------------------------------------------------------------------------------------------------
# 11 User interface
# ----------------------------------------------------------------------------------------------------------
doc.chapter("User interface")
doc.text("The interface is server-rendered (FastAPI and Jinja2) and styled with Bootstrap. Every role has its own menu and "
         "pages. The screenshots in this chapter were taken from a freshly seeded database; the incident INC-1046 "
         "\"Payment page is down\" was reported through the form and then followed through its whole life, so the "
         "pages show real results of the workflow.")
doc.section("Pages for everyone")
shot("01_login", "Sign-in page. A wrong password and an unknown user give the same message.")
shot("02_register", "Registration page submitted empty: each problem is explained next to its field.")
shot("10_notifications", "Notifications: unread ones are highlighted and each leads to its incident.")
shot("23_error_403", "The access-denied page, shown when an employee opens an administrator page.")
shot("24_mobile_view", "The same employee page on a phone-sized screen: the menu collapses and the table scrolls sideways.")
doc.section("Employee")
shot("03_employee_dashboard", "Employee dashboard: the employee's own incidents with status, priority and SLA badges, filterable by status.")
shot("04_report_form", "The report form: service, category, impact, urgency and the number of people affected.")
shot("05_incident_created", "Right after reporting \"Payment page is down\": the system states the priority (P1, score 27), the response and "
                            "resolution deadlines, the technician it assigned and a possible-duplicate warning.")
shot("06_incident_detail", "The incident page: the eight-step progress bar, the details and SLA card, and the timeline built from the audit trail.")
shot("09_reply_box", "After the technician requests information, the reporter sees the question and a reply box.")
shot("25_closed_incident", "A completed incident: Closed on the progress bar, investigation notes, resolution, feedback, the SLA card "
                           "and the full 13-entry timeline.")
doc.section("Technician")
shot("07_technician_dashboard", "Technician dashboard: workload against the maximum, and the assigned incidents, most urgent first.")
shot("08_technician_actions", "The technician's incident page: only the actions that are valid for the current status are offered.")
doc.section("Administrator")
shot("11_admin_dashboard", "Administrator dashboard: overview cards, technician workload and incidents per service.")
shot("12_admin_incident_tools", "Administrator tools on an incident: assign, auto-assign, recommend a technician and override the priority.")
shot("13_recommend_technician", "Technician recommendation: a ranked list with a score and the reasons for each.")
shot("14_search", "Incident search with filters (here: priority P1).")
shot("15_users", "User management: the user table and the form to create a user.")
shot("16_services", "IT services with their business criticality and SLA policy.")
shot("16_categories", "Incident categories and the technician skill each one requires.")
shot("17_sla_policies", "SLA policies: response and resolution targets for each priority.")
shot("18_strategies", "Choice of the assignment and priority strategies; the change applies at once, without a restart.")
shot("19_reports", "Reports: counts, technician workload, incidents per service and category, and the related-incidents report that "
                   "flags a probable problem with a service (three open Network incidents within one hour).")
shot("20_audit_log", "Audit log filtered to one incident: every action with who did it, when, and the status change.")
shot("21_sla_violations", "SLA violations recorded by the monitor.")
shot("22_demo_controls", "Demo controls: move the simulated clock forward and run the SLA and escalation checks immediately.")

# ----------------------------------------------------------------------------------------------------------
# 12 Demonstration
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Project demonstration")
doc.text("The brief asks for at least three complete workflows. The video shows the three workflows below, each "
         "recorded from a freshly seeded database. They map onto the examples in the brief as follows.")
doc.table(["Workflow in the brief", "What the demonstration shows"], [
    ["1. Employee reports, the system prioritises, a technician is assigned, a notification is generated",
     "An employee reports \"Payment page is down\". The system scores it P1, sets 3 and 20 minute deadlines, flags a possible "
     "duplicate, assigns a technician and notifies the technician and the reporter (in the application and in the simulated "
     "e-mail log)."],
    ["2. The technician investigates, the SLA is monitored, the incident is resolved, the user is notified",
     "The technician acknowledges, investigates, adds a note and asks a question; the reporter answers. The demo clock is "
     "moved so the SLA monitor records a warning and a violation. The incident is resolved, verified, closed and rated; "
     "the audit trail lists every step."],
    ["3. Several incidents are reported, duplicates and related incidents are identified, incidents are correlated or escalated",
     "Three open Network incidents are reported as a probable service problem. The seeded critical incident that nobody "
     "acknowledged is escalated to the team lead, then the system administrator, then the IT manager as the clock moves. "
     "Similar payment reports are flagged as possible duplicates."],
], widths=[0.4, 0.6])
add_md("demo_data.md", intro=True)
add_md("demo_script.md", intro=False,
       h2=lambda t: t.startswith(("1.", "4.", "5.", "6.", "7.")),
       replacements=[("(read this first)", ""), ("(about one minute)", ""),
                     ("Segments are joined in an editor afterwards, which is what the plan expects anyway.",
                      "The segments are joined in a video editor afterwards.")])

# ----------------------------------------------------------------------------------------------------------
# 13 Source code and running
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Source code and how to run it")
doc.section("The repository")
doc.text(f"The complete source code is in a public Git repository: **{REPO_URL}**. The folders are organised by layer:")
doc.code("""iitsm/
  app/
    domain/        P1  the domain model: entities, State classes, strategies, SLA engine, intelligence
    ports/         shared interfaces: service and repository contracts, data carriers, the Container
    persistence/   P2  SQLite schema, repositories, demo data seeder
    services/      P3  workflow, security, observers, channels, background jobs, composition root
    web/           P4  routes, templates, forms, error pages, stub mode
    main.py        the application entry point
    config.py      settings read from environment variables
  tests/           automated tests, one folder per layer, plus the architecture test
  docs/            documents, diagrams and screenshots used for this report
  scripts/         domain demo and class diagram generator
  requirements.txt pinned dependencies""")
add_md("run_instructions.md", intro=False)

# ----------------------------------------------------------------------------------------------------------
# 14 Limitations, 15 Conclusion
# ----------------------------------------------------------------------------------------------------------
doc.chapter("Limitations and future work")
doc.section("Known limitations")
doc.text("The limitations below are known and stated openly. Those of the architecture and the database come from the "
         "design documents; the security limitations are in section 9.1.")
add_md("architecture.md", shift=1, intro=False, h2=lambda t: t.startswith("7."),
       replacements=[("- The text diagram above is also available as a rendered picture, `docs/report/diagrams/architecture.png`.\n", "")])
add_md("database_design.md", shift=1, intro=False, h2=lambda t: t.startswith("9."),
       replacements=[("## 9. Known limitations", "## 9. Known limitations of the database layer")])
doc.heading_plain("Web interface and scheduler", 3)
doc.bullets([
    "Pages are server-rendered, so there is no live update: a new notification appears the next time a page is loaded.",
    "Bootstrap is loaded from a CDN, so the pages need internet access to be styled.",
])
doc.section("How the system could evolve")
add_md("architecture.md", shift=1, intro=False, h2=lambda t: t.startswith("6."))
doc.bullets([
    "The duplicate detector matches words, not meaning. A similarity measure based on text embeddings would find more "
    "duplicates, and it fits behind the same detector interface.",
    "A real e-mail or SMS gateway is one more `NotificationChannel` class.",
    "Resolution suggestions from earlier, similar closed incidents could be added as another intelligent feature.",
])

doc.chapter("Conclusion")
doc.text("I-ITSM covers the whole life of an IT incident: reporting, prioritisation, SLA deadlines, assignment, "
         "investigation, resolution, verification and closure, with duplicate detection, correlation, escalation, "
         "notifications and a complete audit trail. The design keeps the rules of the business in one place, the domain "
         "layer, written only with the Python standard library, and lets the layers around it be replaced or tested on their own.")
doc.text("The object-oriented design is visible in the code: the State pattern makes illegal transitions impossible, "
         "the Strategy pattern lets the administrator change the priority and assignment policy while the system runs, "
         "the Observer pattern writes the audit trail and sends notifications without the incident knowing who listens, "
         "and the Repository pattern keeps all SQL in one layer. An automated test enforces the layering, and 815 tests "
         "check behaviour from the domain up to the web pages.")
doc.text("Three complete workflows can be shown in the demonstration, and every step is recorded in the audit log. The "
         "limitations that remain are listed in chapter 14 and none of them prevents the workflows from being shown.")

doc.save(OUT)
print("written", OUT, f"({OUT.stat().st_size // 1024} KB)")

if "--pdf" in sys.argv:                                   # also print the PDF (needs pypdf and websockets, see html_report.py)
    from html_report import render_pdf
    render_pdf(doc.items, OUT.with_suffix(".pdf"))
