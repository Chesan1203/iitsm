# Business rules and algorithms

Every number below lives in one place in the code, `app/domain/business_rules.py` (class `BusinessRules`); nothing else hard-codes them. The lifecycle rules (who may do what in which status) are in `docs/domain_decisions.md`.

## 1. Priority

`score = impact x urgency x business criticality`, each factor 1 (LOW) to 3 (HIGH), so the score is 1 to 27.

| Score | Priority |
|---|---|
| 18 or more | P1 Critical |
| 9 to 17 | P2 High |
| 4 to 8 | P3 Medium |
| 1 to 3 | P4 Low |

- Only ten scores can occur: 1, 2, 3, 4, 6, 8, 9, 12, 18, 27. Over the 27 combinations: P1 = 4 (15%), P2 = 6, P3 = 10, P4 = 7. The reachable P1/P2 boundary is therefore 12 versus 18, and `score_to_priority` is tested at 17/18 directly.
- Multiplying (rather than adding) makes the highest combinations stand out: HIGH x HIGH x HIGH = 27 versus MEDIUM x MEDIUM x MEDIUM = 8. Business criticality belongs to the service, so a payment outage outranks a printer fault of equal impact and urgency.
- **Affected-users bump:** 50 or more affected users raise the priority by exactly one level (P1 stays P1). The score is left as calculated and the explanation says why the priority differs.
- **Strategies** (swappable at run time through `PriorityStrategy`):
  - `weighted_score`: the formula above. (The name is historical: it is a product, not a weighted sum.)
  - `rule_based`: HIGH criticality and HIGH impact is always P1, whatever the urgency; every other case uses `weighted_score` (the second strategy composes the first), including the bump.
- Every result carries a readable explanation, e.g. `3×3×2 = 18, P1` or `3×2×2 = 12, P2; 120 affected users (≥50) raise it to P1`.

## 2. Service level agreement (SLA)

Default targets (response / resolution): P1 5 min / 30 min, P2 15 min / 2 h, P3 1 h / 8 h, P4 4 h / 24 h.

- **Clocks.** Both start at the incident's creation time. The response clock stops at acknowledgement. The resolution clock stops at RESOLVED, and runs again if the reporter rejects the resolution (`resolved_at` is cleared).
- **Warning** at 80 percent of a window; the zone applies only while that clock is still running and its deadline is not yet missed.
- **Violation** strictly after the deadline (exactly at the deadline is not a violation). A late acknowledgement or resolution counts as a violation even if the job only notices later.
- **Four event types**, each recorded at most once per incident: `RESPONSE_WARNING`, `RESOLUTION_WARNING`, `RESPONSE_VIOLATED`, `RESOLUTION_VIOLATED`. The original contract had one `WARNING`, which could not represent the two independent warnings under the unique rule (incident, event type).
- **Status** (recomputed on every check, from the times, not from flags):
  - `VIOLATED` if any deadline was missed. It is sticky: it survives resolution, verification and closure.
  - `MET` if both clocks have stopped and nothing was missed.
  - `WARNING` while a running clock is in its warning zone.
  - `ON_TRACK` otherwise. An unclassified incident has no SLA, so it is ON_TRACK.
- **Evaluation is pure.** `SlaCalculator.evaluate` changes nothing and returns only events not yet flagged on the tracker. `Incident.apply_sla_result` records the flags and status and announces `SLA_WARNING` / `SLA_VIOLATED` events (actor: the system).
- **Changing the priority** (`change_priority`) swaps in a tracker for the new deadlines, counted from the creation time. Violations already recorded are kept (a missed deadline is history); warning flags restart because the new deadlines open new warning windows.

## 3. Technician assignment (Strategy pattern)

All strategies share one eligibility filter: the technician's account is active, they are marked available, and their active incident count is below their own `max_workload` (default 5). Active = ASSIGNED, ACKNOWLEDGED or IN_PROGRESS. `select` is defined once in `AssignmentStrategy` (the first technician of `rank`, or `None`); each strategy only defines `rank` and `name` (Template Method).

| Strategy (`name`) | Who qualifies | Order |
|---|---|---|
| Skill based (`skill_based`) | eligible AND has the category's required skill (case-insensitive) | fewest active incidents, then most experience, then lowest id |
| Load based (`load_based`) | eligible (skills ignored) | same order |
| Weighted recommendation (`weighted_recommendation`), the "smart technician recommendation" | eligible (skill is scored, not required) | score descending, then the same tie-break |

Weighted score, out of 100: `40 x skill match (1 or 0) + 30 x (1 - active / max workload) + 15 x (experience years, capped at 10, / 10) + 15 x (incidents resolved on this service, capped at 5, / 5)`. Each ranked technician carries readable reasons, e.g. "has skill Database", "1 of 5 slots used", "5 years experience", "resolved 5 incidents on this service". For the two simple strategies the score shown is the load component (100 = idle); the order of `rank` is what decides.

Tie-breaks make results predictable and testable: the same input in any order gives the same technician.

## 4. Duplicate incident detection

No machine learning. Per incident: lowercase title (and description) into words, drop stopwords, replace synonyms by a canonical word (down / failing / unable / error ... become FAIL; payment / transaction / checkout become PAYMENT; login / sign in / password become AUTH; and more), then compare the word sets with the Jaccard index (overlap divided by union).

`score = 0.7 x text similarity + 0.3 x (1 if same service)`; an incident is flagged at 0.5 or more. Flag only: nothing is merged or rejected.

- **Text similarity is the better of two comparisons: title only, and title plus description.** Descriptions are mandatory, and a long one would dilute a clear title match, so the title-only comparison stops a wordy description from hiding an obvious duplicate; the combined comparison still catches identical descriptions under different titles.
- Worked example (same service): "Payment application unavailable" vs "Payment transaction failing" share {PAYMENT, FAIL} out of 3 words: 0.7 x 2/3 + 0.3 = 0.77. "Unable to make payment" vs the first: 0.7 x 2/4 + 0.3 = 0.65. "Printer out of paper" on another service shares no words: 0.
- **Limits:** it matches words, not meaning (a synonym missing from the list is invisible), ignores word order and negation, and the lists are English only. Without the same service the text must be about 71 percent identical to reach 0.5.

## 5. Automatic escalation

Applies only to a P1 incident that is still ASSIGNED after its response deadline. Once the deadline has passed (strictly after) the target is TEAM_LEAD; every further 10 minutes it goes one level up: SYSTEM_ADMIN, then IT_MANAGER, where it stays. `evaluate` returns a decision only when the target is higher than the incident's current level, so a scheduled job can poll it every 30 seconds without repeating itself, a late first check jumps straight to the right level, and a manual escalation is respected. Each decision names the admin level to notify.

Timeline for a P1 with a 5 minute response target: 5:00 nothing, 5:01 TEAM_LEAD, 15:00 SYSTEM_ADMIN, 25:00 IT_MANAGER, nothing afterwards.

## 6. Incident correlation

Groups the incidents that are still unresolved (not RESOLVED, VERIFIED or CLOSED) and were created in the last 60 minutes by affected service. A service with two such incidents gets a group; with three or more it is flagged as a probable service-level problem. Groups are listed probable first, then by size.

## 7. Notes for the services layer

The job should call `evaluate`, record one `SlaEvent` per new event type, then call `apply_sla_result` **whenever the result differs from the tracker**, not only when events were recorded: a status-only change (for example WARNING back to ON_TRACK after an acknowledgement, or to MET) has no event but must still be stored. After a priority change, `sla_events` still holds the earlier rows, so a warning for the new deadlines would be blocked by the unique rule (incident, event type); either relax that rule for warnings or accept that each warning type is recorded once per incident.
