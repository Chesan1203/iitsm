# Problem analysis

## 1. The problem

Modern organisations depend on IT services: payment systems, databases, networks, sign-in, email,
cloud storage. When one fails, employees need to report it, and the IT support team has to
identify, prioritise, assign, investigate, resolve and close the incident.

In a large organisation hundreds of incidents arrive every day. Handled by hand (a shared mailbox,
a spreadsheet, a phone call), this goes wrong in predictable ways, and a typical example shows it:

> *"The payment application is unavailable and users cannot complete transactions."*

Three employees report the same outage in three different words. Someone has to notice they are the
same problem, decide that it matters more than a printer fault, pick the right engineer who is free,
make sure that engineer actually looks at it within minutes, tell the people affected, and keep a
record of everything for later.

## 2. Stakeholders

| Stakeholder | What they need |
| --- | --- |
| **Employees** (reporters) | A fast way to report a problem, to see its progress, to answer questions, and to confirm it is really fixed |
| **IT technicians** (support engineers) | To see their own work, most urgent first; a clear record of what they have been asked to do; to ask the reporter for information; a fair workload |
| **IT managers and administrators** | To configure services, categories and SLA policies; to see what is open, late or at risk; to assign work, override priorities and audit what happened |
| **The organisation** | Fewer outages that drag on, evidence that service targets are met, and a complete history for audits |
| **The development team and later maintainers** | A system whose rules can change (a new notification channel, a new assignment rule, a new database) without rewriting unrelated parts |

## 3. Existing challenges

| Challenge | Consequence |
| --- | --- |
| **Delayed response** | Nobody owns a new report, so serious outages wait |
| **Wrong prioritisation** | A trivial request is handled before a critical outage, because priority is guessed |
| **Inefficient technician allocation** | The same skilled person is overloaded while others are idle, or work goes to someone without the skill |
| **SLA violations that nobody sees** | Deadlines are missed silently and discovered only afterwards |
| **Duplicate reports** | Several people report the same problem and effort is wasted, or the real scale of the outage is hidden |
| **Incomplete history** | It is impossible to say who did what and when |
| **Poor visibility** | Managers cannot tell how many incidents are open, which services fail most, or who is overloaded |
| **Unrecognised recurring problems** | Related incidents are handled one by one, so a failing service is not spotted |

## 4. Proposed solution

I-ITSM is a web application that manages the whole lifecycle of an IT incident:

**Report, classify, prioritise, assign, investigate, resolve, verify, close.**

When an employee reports an incident the system, without further human effort:

1. creates the incident and numbers it (INC-1001, INC-1002, ...);
2. classifies it by category and service;
3. calculates the **priority** from impact, urgency, the service's business criticality and the number
   of affected users, and explains the calculation;
4. finds the applicable **SLA** (the service's own policy, otherwise the default) and sets the
   response and resolution deadlines;
5. flags a **possible duplicate** if a similar open incident exists on the same service;
6. chooses a suitable **technician** with the active assignment strategy, or leaves the incident
   unassigned for an administrator when nobody is free;
7. **notifies** the people involved (in the application, and by simulated email);
8. **records every action** in an audit trail;
9. watches the deadlines in the background, records warnings and violations once each, and
   **escalates** an unacknowledged critical incident up the management chain.

Three kinds of user work in three different interfaces:

| Role | Interface |
| --- | --- |
| Employee | Report an incident, track it, answer questions, verify the fix, give feedback |
| Technician | Workload and assigned incidents (most urgent first), acknowledge, investigate, resolve |
| Administrator | Dashboard, all incidents and search, user / service / category / SLA management, strategy selection, reports, audit log, SLA violations, and demo controls |

The design question the project answers is how object-oriented thinking can make such a system
**maintainable, extensible and intelligent**. The architecture (`docs/architecture.md`) separates
the business rules, the database, the workflow and the web pages, so each can be tested and changed on
its own.

## 5. Scope

**Included** (the brief's minimum viable product): three user roles; create, view, update, assign,
resolve and close incidents; priority from impact, urgency and criticality; two or more assignment
strategies; SLA calculation, deadline tracking and violation detection; two notification mechanisms;
a complete audit trail; five or more search criteria; reports; two or more intelligent features
(duplicate detection, escalation, smart technician recommendation, correlation); persistence;
exception handling; and basic security.

**Deliberately not included** (optional in the brief): real email or SMS delivery, real-time push
notifications, machine learning, cloud deployment or containers, a JavaScript front end, a mobile app.
`docs/architecture.md` explains how the system could grow towards several of these.

## 6. Assumptions

- One organisation uses the system; there is no multi-tenancy.
- Email is **simulated**: messages are written to a log file in a readable form, not delivered.
- One default SLA table (response and resolution time per priority) applies, and a service may have its
  own stricter policy. SLA clocks run in continuous time, not working hours.
- Priority is calculated by a documented rule (score = impact x urgency x criticality, with a bump for 50
  or more affected users), not learned from history. A well-designed rule-based system is acceptable
  under the brief.
- A technician has a maximum number of active incidents (5 by default) and a list of skills, and each
  category names the skill it needs.
- Duplicate detection compares words, with a small list of synonyms (for example "unavailable", "down"
  and "failing" count as the same). It only flags a possible duplicate; it never merges or rejects.
- Users sign in with a username and password. Technician and administrator accounts are created by an
  administrator; anyone may register as an employee.
- A single application server and a single SQLite database file are enough for the expected load
  (hundreds to a few thousand incidents).
- A demonstration needs deadlines to pass quickly, so the system has a **simulated clock** that an
  administrator can move forward, and buttons to run the SLA and escalation checks on demand. These work
  only when `SIMULATED_TIME` is on.
- The demo data are fictional.
