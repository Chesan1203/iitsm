# Screenshots for the report

The report needs UI screenshots for each role. They could not be saved automatically, so take them
yourself from a **fresh seeded database** (see `docs/run_instructions.md`) and save each as a PNG in this
folder with the file name shown. Use a wide browser window (at least 1200 pixels) at 100 percent zoom so the
desktop layout appears, and make sure the page is fully loaded (the styling comes from the internet).

All passwords are `Password@123`. If a step needs data that the seed does not have, the third column says
how to create it.

| File name | Sign in as | Page | What it should show / how to get it |
| --- | --- | --- | --- |
| `01_login.png` | nobody | `/login` | The sign-in form |
| `02_register.png` | nobody | `/register` | Submit it empty to show the field errors beside the inputs |
| `03_employee_dashboard.png` | `emp1` | `/employee/dashboard` | The list of the employee's own incidents with status, priority and SLA badges |
| `04_report_form.png` | `emp1` | `/incidents/new` | The report form with the impact and urgency explanations |
| `05_incident_created.png` | `emp1` | after submitting the form | Report "Payment page is down" (Payment, Application, High, High, 120). Capture the confirmation messages (priority P1, score 27, deadlines, assignment, duplicate warning) |
| `06_incident_detail.png` | `emp1` | `/incidents/{id}` | The progress bar, SLA card, details and timeline of that incident |
| `07_technician_dashboard.png` | the technician it was assigned to | `/tech/dashboard` | The workload bar and the assigned incidents, most urgent first |
| `08_technician_actions.png` | the same technician | the incident page | The Acknowledge / Start / Note / Resolve forms (press Acknowledge and Start first so the resolve form shows) |
| `09_reply_box.png` | `emp1` | the incident page | After the technician presses Request information, the reply box with the question |
| `10_notifications.png` | any user | `/notifications` | Unread (highlighted) and read notifications |
| `11_admin_dashboard.png` | `admin1` | `/admin/dashboard` | Overview cards, technician workload bars, incidents per service |
| `12_admin_incident_tools.png` | `admin1` | the incident page | The Administrator tools panel (assign, auto-assign, recommend, priority override) |
| `13_recommend_technician.png` | `admin1` | `/incidents/{id}/recommend` | The ranked technicians with scores and reasons |
| `14_search.png` | `admin1` | `/incidents/search` | Choose a few filters (for example priority P1 and status In progress) and press Search |
| `15_users.png` | `admin1` | `/admin/users` | The user table and the create form |
| `16_services_categories.png` | `admin1` | `/admin/services` (and `/admin/categories`) | The tables and the add form (two screenshots if you prefer) |
| `17_sla_policies.png` | `admin1` | `/admin/sla-policies` | Policy cards with readable durations and the editor |
| `18_strategies.png` | `admin1` | `/admin/strategies` | The assignment and priority strategy choices |
| `19_reports.png` | `admin1` | `/admin/reports` | The tables and the "Probable service problem" card. **Take this before moving the demo clock** |
| `20_audit_log.png` | `admin1` | `/admin/audit` | The filters and records (filter to one incident for a clear timeline) |
| `21_sla_violations.png` | `admin1` | `/admin/sla-violations` | After running the demo steps so at least one row exists |
| `22_demo_controls.png` | `admin1` | `/admin/demo` | The simulated time, the +5 / +15 / +30 / +60 buttons and the check buttons |
| `23_error_403.png` | `emp1` | `/admin/dashboard` | The access-denied page |
| `24_mobile_view.png` | any | any page | Browser developer tools in phone size, to show the responsive layout (optional) |
