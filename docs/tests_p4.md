# P4 test cases: web layer

The web layer has **269 automated tests** in `tests/web/` (the whole project has 815). Run them with
`pytest tests/web`. The table documents 21 of them, covering all six required categories.

The tests drive the real application through FastAPI's `TestClient`, signing in as real users and
following redirects as a browser would. They run the **real services over in-memory repositories**, so a page
is tested against genuine behaviour, not a hand-written copy of it. A smaller set runs the same pages in
**stub mode**, and one set of tests in `tests/services/test_wiring.py` runs the full workflows on a real
seeded SQLite database.

Mutation testing guarded the important rules: I deliberately broke a rule (removed a role check, offered
the Resolve button in every status, brought back the flash-message bug, and so on) and confirmed that tests
failed. Some guards cannot be distinguished by any test, because the service refuses the same user with the
same 403 even when the route's role guard is loosened. They are kept as defence in depth.

Result of the last run: all 269 web tests passed (full project: 815 passed, also in a brand-new virtual environment built from `requirements.txt`).

| ID | Module | Category | Input or steps | Expected | Actual | Pass? |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | Access control | Authorization | Request `/`, `/notifications` and the three dashboards without signing in | Each redirects to `/login` (and remembers the page asked for) | All five redirected; `/notifications` gave `/login?next=/notifications` | Pass |
| W2 | Access control | Authorization | Employee opens the admin and technician dashboards; technician opens the admin and employee dashboards; administrator opens the employee and technician dashboards; each role opens its own dashboard | Another role's page gives 403; the role's own page gives 200 | 6 combinations gave 403 with a permission message; 4 gave 200 | Pass |
| W3 | Report form | Invalid input | Submit the report form with a blank title and description, no service or category, and 0 affected users | The form again (400), with an error beside the field, and nothing saved | 400; the title field flagged invalid; error text shown; no incident created | Pass |
| W4 | Incident actions | Exception | An employee presses Close on an ASSIGNED incident (and, in stub mode, a technician acts on incident 999) | A redirect back to the incident page showing the invalid-transition message; the status is unchanged | Redirected to the incident page; "Cannot close an incident that is ASSIGNED" shown in a red alert; status still ASSIGNED. In stub mode the message named incident 999. | Pass |
| W5 | Menus | Normal | Sign in as an employee, a technician and an administrator | Each sees only its own menu | The navigation links matched the defined menu for each role; the three menus differ | Pass |
| W6 | Login | Invalid input | Sign in with a wrong password, and with an unknown username | The login page again with the same generic message, no session, the username kept, the password never shown | Status 401 both times with "Invalid username or password"; no session cookie; `value="emp1"` kept; password absent from the page | Pass |
| W7 | Incident page | Business rule | A technician opens the incident in each status | Resolve is offered only while IN_PROGRESS (Acknowledge only when ASSIGNED, Start only when ACKNOWLEDGED) | Matched at every step; the same held in stub mode for the in-progress sample incident | Pass |
| W8 | Action routes | Authorization | The wrong person (an employee, an unassigned technician, an administrator, another reporter) posts to acknowledge, assign, verify, feedback, note or priority | 403 and the incident is unchanged | 10 combinations gave 403; the incident stayed ASSIGNED | Pass |
| W9 | Whole workflow | Normal | Through the pages: report, acknowledge, start, note, request information, reply, resolve, verify, close, feedback | Every step redirects to the incident page; the final page shows Closed, the resolution, the feedback and a full timeline | All 9 actions gave 303 to the incident; the page showed Closed, "Restarted gateway", rating 4 and all steps in the timeline | Pass |
| W10 | Login redirect | Invalid input | Sign in with a `next` value of `//evil.example`, `https://evil.example` or `/\evil.example`, and with `/notifications` | Only a plain path on this site is followed; anything else goes to the user's home page | The three outside addresses went to `/employee/dashboard`; `/notifications` was honoured | Pass |
| W11 | Hidden fields | Business rule | Report an incident with extra form fields `reporter_id`, `user_id`, `status=CLOSED` and `priority=P4` | The extras are ignored: the reporter is the signed-in user, and status and priority come from the system | Reporter emp1; status not CLOSED; priority P1 | Pass |
| W12 | Report form | Boundary | Submit 0 affected users, "many", an unknown impact, a blank urgency, an unknown service and category (9 cases) | Each is rejected on that field and nothing is saved | All 9 gave 400 with the field flagged; no incident created | Pass |
| W13 | Sessions | Authorization | An administrator deactivates a signed-in employee, then reactivates them | The old session ends at the next request and does not come back; a fresh sign-in works | Redirected to `/login` both times; a new login reached the dashboard | Pass |
| W14 | Error pages | Exception | A route raises an unexpected error containing a secret path | A generic 500 page with no details or stack trace | 500 "Something went wrong on our side."; the secret text and "Traceback" absent | Pass |
| W15 | Admin tools | Business rule | An administrator overrides a P1 incident to P3 | The priority and badge change, the SLA deadlines are recalculated from creation, and the technician and reporter are notified | Badge P3; deadlines 11:00 and 18:00; a PRIORITY_CHANGED audit record and notification; a repeat gives "Priority is already P3" | Pass |
| W16 | Demo controls | Business rule | On the simulated clock: report a P1, run the escalation check, move the clock 6 minutes, run it, then 10 more | 0 escalated; 1 (Team lead); 0 on a repeat; 1 (System admin) | Matched, and the incident page showed each new level | Pass |
| W17 | Admin forms | Invalid input | Save an SLA policy with a blank target, text instead of minutes, response longer than resolution, a zero target, and a blank name | A message is always shown, the other entries are kept, nothing changes | All 5 gave 400 with a message and `value="10"` kept; still one policy | Pass |
| W18 | Messages | Normal | Create an incident (leaving its confirmation waiting) and then trigger a refused action | Both messages appear on the next page | Both shown. (Regression test: the second message used to be lost.) | Pass |
| W19 | Output safety | Authorization | Enter `<script>alert(1)</script>` as an incident title and description | The text is shown as text; nothing runs | `&lt;script&gt;` present, the raw tag absent | Pass |
| W20 | Session cookie | Authorization | Sign in and read the session cookie | The cookie is `HttpOnly` and `SameSite=Lax` | Both flags present | Pass |
| W21 | Route coverage | Authorization | Walk every route of the running application: anonymous visitors, then each role that is not allowed | Every route is public on purpose or matches an access rule; anonymous visitors are redirected to the login page from all protected routes; every disallowed role gets 403 before the route does anything | All 56 operations classified; every protected route redirected anonymous visitors; every disallowed role got 403; nothing was created. A route added to an unguarded router, or with no access rule, makes the tests fail | Pass |

## Where each ID lives

| ID | Test function | File |
| --- | --- | --- |
| W1 | `test_w1_anonymous_requests_to_protected_pages_redirect_to_login` | `test_auth_and_access.py` |
| W2 | `test_w2_each_role_reaches_only_its_own_pages` | `test_auth_and_access.py` |
| W3 | `test_w3_a_blank_form_shows_an_error_beside_each_field_and_keeps_what_was_typed` | `test_incident_pages.py` |
| W4 | `test_w4_an_illegal_transition_shows_the_message_on_the_incident_page`, `test_w4_in_stub_mode_incident_999_shows_the_invalid_transition_message` | `test_incident_pages.py` |
| W5 | `test_w5_each_role_sees_its_own_menu` | `test_auth_and_access.py` |
| W6 | `test_w6_a_wrong_password_shows_the_generic_message_and_stays_on_the_login_page` | `test_auth_and_access.py` |
| W7 | `test_w7_the_technician_is_offered_only_the_actions_valid_for_the_status`, `test_w7_in_stub_mode_resolve_is_offered_only_for_the_in_progress_incident` | `test_incident_pages.py` |
| W8 | `test_the_wrong_person_cannot_use_an_action_route` | `test_incident_pages.py` |
| W9 | `test_a_complete_workflow_through_the_pages` | `test_incident_pages.py` |
| W10 | `test_only_a_plain_path_on_this_site_is_used_after_login` | `test_auth_and_access.py` |
| W11 | `test_the_reporter_always_comes_from_the_session_never_from_the_form` | `test_incident_pages.py` |
| W12 | `test_each_bad_field_is_reported_on_that_field_and_nothing_is_saved` | `test_incident_pages.py` |
| W13 | `test_a_session_ended_by_deactivation_does_not_come_back_when_the_account_is_reactivated` | `test_auth_and_access.py` |
| W14 | `test_an_unexpected_error_shows_a_generic_500_page_without_details` | `test_auth_and_access.py` |
| W15 | `test_overriding_the_priority_recalculates_the_deadlines_and_notifies` | `test_incident_pages.py` |
| W16 | `test_the_escalation_demo_runs_from_the_pages` | `test_admin_pages.py` |
| W17 | `test_bad_policy_forms_are_explained_and_nothing_changes` | `test_admin_pages.py` |
| W18 | `test_two_messages_in_a_row_are_both_shown_not_just_the_first` | `test_incident_pages.py` |
| W19 | `test_text_on_the_incident_page_is_escaped` | `test_incident_pages.py` |
| W20 | `test_the_session_cookie_is_http_only_and_same_site_lax` | `test_auth_and_access.py` |
| W21 | `test_every_route_is_public_on_purpose_or_has_an_access_rule`, `test_anonymous_visitors_are_redirected_to_login_from_every_protected_route`, `test_every_role_that_is_not_allowed_gets_403_before_the_route_does_anything` | `test_route_coverage.py` |

## What the other tests cover

- **`test_auth_and_access.py` (49):** login, registration, logout, sessions, the role guards, menus and the
  error pages.
- **`test_dashboards_and_notifications.py` (19):** the three dashboards, badge colours, the notification bell
  and notification pages.
- **`test_incident_pages.py` (76):** the report form, the incident page and its buttons for every role and
  status (including a direct test of the `allowed_actions` function), every action route, the administrator
  incident tools, search, and the same pages in stub mode.
- **`test_admin_pages.py` (85):** users, services, categories, SLA policies, strategies, reports, the audit
  log, SLA violations and the demo controls, with and without the simulated clock.
- **`test_route_coverage.py` (10):** a sweep over every route of the application, so that a new route cannot be added without a guard and an access rule.
- **`test_stub_mode.py` (30):** every stub service method, the domain rules inside the stubs, and incident 999.
