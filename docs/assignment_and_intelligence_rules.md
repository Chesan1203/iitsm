# Assignment and intelligent features (T7, T8)

Reuse in `docs/business_rules.md` and `docs/oop_and_patterns.md` (task T10).

## Technician assignment (Strategy pattern)

All strategies share one eligibility filter: the technician's account is active, they are marked available, and their active incident count is below their own `max_workload` (default 5). Active = ASSIGNED, ACKNOWLEDGED or IN_PROGRESS. `select` is defined once in `AssignmentStrategy` (the first technician of `rank`, or `None`); each strategy only defines `rank` and `name` (Template Method).

| Strategy (`name`) | Who qualifies | Order |
|---|---|---|
| Skill based (`skill_based`) | eligible AND has the category's required skill (case-insensitive) | fewest active incidents, then most experience, then lowest id |
| Load based (`load_based`) | eligible (skills ignored) | same order |
| Weighted recommendation (`weighted_recommendation`), the "smart technician recommendation" | eligible (skill is scored, not required) | score descending, then the same tie-break |

Weighted score, out of 100: `40 x skill match (1 or 0) + 30 x (1 - active / max workload) + 15 x (experience years, capped at 10, / 10) + 15 x (incidents resolved on this service, capped at 5, / 5)`. Each ranked technician carries readable reasons, e.g. "has skill Database", "1 of 5 slots used", "5 years experience", "resolved 5 incidents on this service". For the two simple strategies the score shown is the load component (100 = idle); the order of `rank` is what decides.

Tie-breaks make results predictable and testable: the same input in any order gives the same technician.

## Duplicate incident detection

No machine learning. Per incident: lowercase title (and description) into words, drop stopwords, replace synonyms by a canonical word (down / failing / unable / error ... become FAIL; payment / transaction / checkout become PAYMENT; login / sign in / password become AUTH; and more), then compare the word sets with the Jaccard index (overlap divided by union).

`score = 0.7 x text similarity + 0.3 x (1 if same service)`; an incident is flagged at 0.5 or more. Flag only: nothing is merged or rejected.

- **Text similarity is the better of two comparisons: title only, and title plus description.** Descriptions are mandatory, and a long one would dilute a clear title match, so the title-only comparison stops a wordy description from hiding an obvious duplicate; the combined comparison still catches identical descriptions under different titles.
- Worked example (same service): "Payment application unavailable" vs "Payment transaction failing" share {PAYMENT, FAIL} out of 3 words: 0.7 x 2/3 + 0.3 = 0.77. "Unable to make payment" vs the first: 0.7 x 2/4 + 0.3 = 0.65. "Printer out of paper" on another service shares no words: 0.
- **Limits:** it matches words, not meaning (a synonym missing from the list is invisible), ignores word order and negation, and the lists are English only. Without the same service the text must be about 71 percent identical to reach 0.5.

## Automatic escalation

Applies only to a P1 incident that is still ASSIGNED after its response deadline. Once the deadline has passed (strictly after) the target is TEAM_LEAD; every further 10 minutes it goes one level up: SYSTEM_ADMIN, then IT_MANAGER, where it stays. `evaluate` returns a decision only when the target is higher than the incident's current level, so a scheduled job can poll it every 30 seconds without repeating itself, a late first check jumps straight to the right level, and a manual escalation is respected. Each decision names the admin level to notify.

Timeline for a P1 with a 5 minute response target: 5:00 nothing, 5:01 TEAM_LEAD, 15:00 SYSTEM_ADMIN, 25:00 IT_MANAGER, nothing afterwards.

## Incident correlation

Groups the incidents that are still unresolved (not RESOLVED, VERIFIED or CLOSED) and were created in the last 60 minutes by affected service. A service with two such incidents gets a group; with three or more it is flagged as a probable service-level problem. Groups are listed probable first, then by size.
