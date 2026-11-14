# Domain decisions (T3)

Gaps in the plan's lifecycle table, and how the code resolves them. Reuse these in
`docs/oop_and_patterns.md` and `docs/business_rules.md` (task T10).

| # | Question | Decision |
|---|---|---|
| 1 | Feedback after CLOSED (table 5.8 says CLOSED allows nothing) | `ClosedState` allows exactly one action: the reporter's one-time `submit_feedback`. |
| 2 | Actions allowed in "any status except CLOSED" | One parent class, `OpenState`, holds `add_note`, `escalate`, `change_priority`, `mark_possible_duplicate`, `apply_sla_result`. Every state except `ClosedState` inherits it, so each rule is written once. |
| 3 | Who may add notes, and when | Assigned technician: INVESTIGATION notes from ASSIGNED to RESOLVED. Reporter: INFO_RESPONSE notes in any open state. INFO_REQUEST notes only through `request_info`. |
| 4 | `respond_to_info` with no question pending | Rejected with `InvalidStateTransitionError`. Pending means: the latest INFO_REQUEST/INFO_RESPONSE note is an INFO_REQUEST (`Incident.has_pending_info_request`). Investigation notes do not clear it. |
| 5 | Effect of `reject_resolution` | Status returns to IN_PROGRESS; `resolved_at` and `resolution` are cleared (they would be stale). The rejected summary and the reason are kept in the audit event description. The SLA resolution clock therefore runs again (matters for T6). |
| 6 | `change_priority` | Updates `priority` and swaps the SLA tracker; `priority_score` is left as originally calculated; the admin's reason goes into the event. Not allowed before classification; same-priority change is rejected. |
| 7 | Observer failures | The plan's behaviour is kept: a failing observer never undoes the incident change. It is logged at ERROR level with the traceback and the remaining observers still run (`Incident._fire`, task T4). |

Other rules fixed in T3:
- **Who counts as an administrator.** `User.system()` has role ADMINISTRATOR. `require_admin_or_system` accepts it; `require_admin` (reassign) and `require_reporter_or_admin` (verify, close) accept human administrators only.
- **Users are compared by id** in permission checks, so an unsaved user (id None) is never treated as the reporter or technician.
- **Illegal state beats missing permission, which beats invalid data** (plan 5.8), for predictable errors.
- **`apply_sla_result`** exists in `OpenState` but raises `NotImplementedError` until T6.
