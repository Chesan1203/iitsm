# P3 test cases: services, security, notifications and background jobs

The services layer has **266 automated tests** in `tests/services/` (the whole project has 815).
Run them with `pytest tests/services`. The table documents 15 of them, covering all six required
categories. Unit tests use in-memory fake repositories. A parity test runs the same scenario through
the fakes and through the real SQLite repositories and demands identical answers, so the fakes
cannot drift from reality. The integration tests run on a real seeded SQLite database.

How well the tests guard the rules was checked by **mutation testing**: I deliberately broke a rule
(for example removed the "record once only" check, or swapped the two job callables in the wiring) and
confirmed that tests failed each time. Two cases are honest exceptions: removing the service-level
"may this user see the incident" check does not fail any test, because the domain's own permission
checks already refuse the same users (it is kept as defence in depth); and the first version of the
priority-override test did not catch a mutant until the clock was advanced between creation and
override, which is now tested.

Result of the last run: all 266 passed (full project: 815 passed).

| ID | Module | Category | Input or steps | Expected | Actual | Pass? |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Authentication | Invalid input | Log in with a wrong password; with an unknown username; with a correct password on a deactivated account | The same generic `InvalidLoginError("Invalid username or password")` each time | Identical message all three times | Pass |
| S2 | Incident service | Authorization | A different employee, and a technician who is not assigned, read an incident; the reporter, assigned technician and an administrator do the same | The first two raise `UnauthorizedOperationError`; the others succeed; their audit trail is refused too | Matched | Pass |
| S3 | Incident service | Normal | An employee reports a P1 payment incident | Status ASSIGNED; audit trail CREATED, CLASSIFIED, ASSIGNED; reporter and all administrators notified on creation, technician and reporter on assignment | Matched; 6 stored in-app notifications (4 + 2), and the second channel received the same recipients. The real simulated-email log is checked in `test_observers.py` (4 email blocks for a creation). | Pass |
| S4 | Incident service | Exception | Create an incident when no SLA policy exists at all | `MissingSlaConfigurationError`, and nothing saved (no incident, no audit record) | Raised; the incident list and audit log were empty | Pass |
| S5 | SLA monitor job | Business rule | Advance the clock to 80 percent of the response deadline and run the job three times | One warning recorded, nothing on the 2nd and 3rd run; tracker status WARNING | One `RESPONSE_WARNING` row, one audit entry, counts 1, 0, 0 | Pass |
| S6 | Escalation job | Business rule | An unacknowledged P1; run at the deadline, then 5.5, 15.5 and 25.5 minutes in, then much later | Nothing at the deadline; TEAM_LEAD, SYSTEM_ADMIN, IT_MANAGER in order; nothing afterwards; each step notifies that level's administrators and the technician | Matched; exactly 3 ESCALATED audit entries | Pass |
| S7 | Strategy registry / incident service | Business rule | Skill-based assigns to the skilled technician; switch to load-based; create another incident | The next incident goes to the least-loaded technician, with no restart | Skilled technician first, then the idle one, then skill-based again | Pass |
| S8 | Admin service | Authorization | Call each of the 25 admin methods as an employee, a technician, the system actor and nobody | Every call raises `UnauthorizedOperationError` | 100 of 100 refused | Pass |
| S9 | Incident service | Boundary | Resubmit the same title 9 minutes after the first report, then 11 minutes after | Rejected at 9 minutes (the message names the earlier ticket), accepted at 11 | Matched | Pass |
| S10 | Authentication | Invalid input | Register with a 1-character username, a 5-character password, a malformed email, a blank name, and an existing username | `InvalidInputError` each time naming the field | Fields username, password, email, full_name, username | Pass |
| S11 | Admin service | Business rule | Save a new policy as the default | The old default is demoted, exactly one default remains, and the old policy keeps its targets. Trying to unset the only default is refused. | Matched | Pass |
| S12 | Observers | Exception | One notification channel raises on every send | The other channels still deliver, the audit record is still written, and the incident change stands | 4 in-app notifications, 2 audit records, status CLASSIFIED | Pass |
| S13 | SLA monitor job | Business rule | Resolve an incident within its SLA and run the job | Stored SLA status becomes MET with no event and no audit noise; later runs change nothing | MET stored, audit trail unchanged, no event rows | Pass |
| S14 | Wiring (real database) | Normal | On a seeded SQLite database: find the correlated Network incidents, run the escalation check, advance the demo clock 4, 10 and 10 minutes | One probable service problem (Network, 3 incidents); the planted P1 escalates one level per step; the IT manager receives an "escalated" notification | Matched | Pass |
| S15 | Password hasher | Boundary | Hash an 80-byte password; verify a 100-character password against a valid hash | Hashing gives an input error naming `password`; verifying returns False, and neither crashes | `InvalidInputError` (field `password`); `False` | Pass |

## Where each ID lives

| ID | Test function | File |
| --- | --- | --- |
| S1 | `test_wrong_password_unknown_user_and_inactive_account_fail_identically` | `test_security.py` |
| S2 | `test_an_employee_cannot_read_another_employees_incident` | `test_incident_service.py` |
| S3 | `test_creating_an_incident_leaves_an_audit_trail_and_notifies_both_audiences` | `test_incident_service.py` |
| S4 | `test_missing_sla_configuration_raises_and_creates_nothing` | `test_incident_service.py` |
| S5 | `test_a_warning_is_recorded_once_at_80_percent_and_not_again` | `test_jobs.py` |
| S6 | `test_an_unacknowledged_p1_escalates_through_the_chain_in_order` | `test_jobs.py` |
| S7 | `test_switching_the_assignment_strategy_changes_the_next_assignment_without_a_restart` | `test_incident_service.py` |
| S8 | `test_non_administrators_are_refused_by_every_admin_method` | `test_admin_services.py` |
| S9 | `test_exact_resubmission_within_ten_minutes_is_rejected_then_allowed_later` | `test_incident_service.py` |
| S10 | `test_register_rejects_bad_input_naming_the_field` | `test_security.py` |
| S11 | `test_a_new_default_policy_demotes_the_old_one_so_exactly_one_default_remains` | `test_admin_services.py` |
| S12 | `test_a_failing_channel_does_not_stop_the_others_or_the_audit_or_the_incident` | `test_observers.py` |
| S13 | `test_an_incident_resolved_in_time_ends_as_met_without_any_event` | `test_jobs.py` |
| S14 | `test_workflow_3_related_incidents_are_correlated_and_an_unacknowledged_p1_escalates` | `test_wiring.py` |
| S15 | `test_hashing_an_over_long_password_is_an_input_error_not_a_crash` | `test_security.py` |

## What the other tests cover

- **`test_fakes.py` (7):** every fake saves and loads; the parity test against SQLite.
- **`test_security.py` (28):** hashing, input rules, user factory, login, registration, access policy.
- **`test_observers.py` (9):** recipients for every event type, both channels, failure isolation,
  observer re-attachment.
- **`test_admin_services.py` (150):** admin, lookup, report and notification services, the strategy
  registry, the demo clock (most of the count comes from the 100 authorization combinations).
- **`test_incident_service.py` (42):** creation, validation, duplicates, assignment, every lifecycle
  action, search scoping, priority override.
- **`test_jobs.py` (17):** SLA monitor, escalation job, scheduler.
- **`test_wiring.py` (13):** assembling the container over fakes, and the three demo workflows on a
  real seeded database.
