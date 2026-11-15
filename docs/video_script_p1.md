# P1 video clip: domain core (3 to 5 minutes)

Record one continuous screen capture with your face or voice. Before recording: `source .venv/bin/activate`, `clear`, make the terminal font large, open `app/domain/state/states.py` and `app/domain/state/incident_state.py` in VS Code. Rehearse twice. Replace [your name] with yours.

## Running order

| Time | On screen | Say (in your own words) |
|---|---|---|
| 0:00 | Face / project folder | "Hi, I'm [your name]. I built the domain layer: the objects and rules of the incident system, in pure Python. No web, no database. Three things to show: the lifecycle, swappable strategies, and the intelligent features." |
| 0:20 | Terminal: `pytest -q` | "All tests pass. Two of them guard the design: one scans every import and fails if the domain touches a framework or the database, the other checks that nothing in the domain reads the clock, so the demo can fast-forward time." |
| 0:50 | Terminal: `clear` then `python scripts/domain_demo.py`; stop at section 1 | "Section 1 walks one incident through its whole lifecycle. Each line is an event that an observer hears. This is the Observer pattern: the incident does not know who is listening. The audit trail and the notifications in the services layer plug in the same way." |
| 1:20 | Scroll to section 2; then show `incident_state.py` (the `_illegal` method) and `AssignedState` in `states.py` | "Illegal jumps fail by construction. This is the State pattern: one class per status. The base class makes every action illegal. Each state overrides only what is legal there. `NewState` has no `close`, so NEW to CLOSED raises `InvalidStateTransitionError`. Checks always run in the same order: is it legal in this state, is this person allowed, is the data valid. That is why an employee acknowledging gets an unauthorized error, and a workload of five gets `WorkloadExceededError`." |
| 2:15 | Section 3 | "Strategy pattern. Same incident, two priority policies behind one interface. Weighted score gives P2; the rule-based policy says high criticality plus high impact is always P1. The service layer can switch between them without a restart." |
| 2:40 | Section 7 | "Same idea for assignment. Skill-based, load-based and the weighted recommendation pick three different technicians from the same list, and the recommendation explains itself: skill, load, experience, history on this service." |
| 3:05 | Section 4 | "Duplicate detection with no machine learning: remove filler words, map synonyms like 'unable', 'failing' and 'down' to one word, compare word sets with the Jaccard index, add a bonus for the same service. The three payment reports flag each other; the printer report flags nothing. Limit: it matches words, not meaning." |
| 3:40 | Sections 5 and 6 | "SLA clocks are pure: `evaluate` changes nothing and returns only new events, so a job can poll every 30 seconds without repeating itself. A warning at 80 percent, a violation after the deadline, and violations are sticky. An unacknowledged P1 escalates to team lead, then system administrator, then IT manager, ten minutes apart." |
| 4:20 | Back to face / folder | "Everything is documented in `docs/`: the class diagrams, the patterns write-up, the business rules and a read-me with one line per class. Thanks." |

## Likely questions and one-line answers

- **Why State and not if/else?** Each rule is written once in the class of the status it belongs to; adding a status adds a class; illegal transitions cannot be reached.
- **Why does `Incident` not store its state object?** The state is derived from `status` on demand through the factory, so a restored incident works in any status and there is no second copy of the truth.
- **How do you protect private fields in Python?** Underscore names, read-only properties, no setters (a test forbids them), write-once ids, frozen value objects, and validated constructors. Python cannot forbid `inc._status = ...`; it is a discipline enforced by review and tests.
- **Why is time a parameter?** So behaviour is deterministic and testable and the demo can simulate time; the only clock is `TimeProvider`.
- **Why can a failing observer not break an incident?** The change is already complete when observers run; a failure is logged and the others still run. Trade-off: that observer misses the event.
- **What are the limits of duplicate detection?** Word matching only: English, no negation, synonym lists are hand-made.
- **Which patterns are in the domain?** State, Strategy (two families), Observer; plus Template Method, a shared-instance factory and composition.

## Handover checklist (Wednesday night)

- [ ] Everything merged to `main`, tagged `domain-v1.0` (and `domain-v1.0.1` for the final hardening)
- [ ] `pytest` fully green on `main`
- [ ] `docs/DOMAIN_README.md`, `docs/oop_and_patterns.md`, `docs/business_rules.md`, `docs/class_diagram*.png` committed
- [ ] This video clip recorded and sent to whoever assembles the final video
- [ ] Message sent: "Domain is final. Start with `docs/DOMAIN_README.md`; its last section says where to look if a bug appears. Run `python scripts/domain_demo.py` to see everything working."
