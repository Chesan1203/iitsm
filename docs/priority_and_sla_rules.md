# Priority and SLA rules (T5, T6)

Reuse in `docs/business_rules.md` (task T10).

## Priority

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

## SLA

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

## Note for the scheduled job (P3's `SlaMonitorJob`)

The job should call `evaluate`, record one `SlaEvent` per new event type, then call `apply_sla_result` **whenever the result differs from the tracker**, not only when events were recorded: a status-only change (for example WARNING back to ON_TRACK after an acknowledgement, or to MET) has no event but must still be stored. After a priority change, `sla_events` still holds the earlier rows, so a warning for the new deadlines would be blocked by the unique rule (incident, event type); either relax that rule for warnings or accept that each warning type is recorded once per incident.
