# Use cases

The rendered diagram used in the report is `docs/report/diagrams/usecase.png`, drawn by
`docs/report/tools/draw_diagrams.py`. An equivalent PlantUML source, [`use_case_diagram.puml`](use_case_diagram.puml),
can be rendered at <https://www.plantuml.com/plantuml>.

**Actors:** Employee, Technician, Administrator, and the Scheduler (the system itself, acting on a timer).

## Use cases by actor

| Actor | Use case | Where in the application |
| --- | --- | --- |
| Everyone | Register (employees only) and sign in | `/register`, `/login` |
| Everyone | View notifications | `/notifications` |
| Everyone | Search incidents (results limited to what they may see) | `/incidents/search` |
| Everyone | View an incident and its timeline | `/incidents/{id}` |
| Employee | **Report an incident** | `/incidents/new` |
| Employee | Add information or answer a technician's question | incident page |
| Employee (or an administrator) | Verify the fix, close the incident | incident page |
| Employee | Reject the fix, give feedback | incident page |
| Employee | See my incidents | `/employee/dashboard` |
| Technician | See my workload and assigned incidents | `/tech/dashboard` |
| Technician | Acknowledge, start investigating, add notes | incident page |
| Technician | Request information from the reporter | incident page |
| Technician | Resolve the incident | incident page |
| Administrator | See the overview dashboard | `/admin/dashboard` |
| Administrator | Assign or reassign a technician, auto-assign | incident page |
| Administrator | Recommend a technician (ranked, with reasons) | `/incidents/{id}/recommend` |
| Administrator | Override a priority | incident page |
| Administrator | Manage users and technician availability | `/admin/users` |
| Administrator | Manage services, categories and SLA policies | `/admin/services`, `/admin/categories`, `/admin/sla-policies` |
| Administrator | Choose the assignment and priority strategies | `/admin/strategies` |
| Administrator | View reports, correlated incidents and SLA violations | `/admin/reports`, `/admin/sla-violations` |
| Administrator | View the audit log | `/admin/audit` |
| Administrator | Use the demo controls (move the clock, run checks) | `/admin/demo` |
| Scheduler | Monitor SLA deadlines, record warnings and violations | every 30 seconds |
| Scheduler | Escalate an unacknowledged critical incident | every 30 seconds |

## Automatic steps ("include" relationships)

Reporting an incident always includes: calculating the **priority**, determining the **SLA deadlines**,
**assigning a technician automatically** (when someone is free), **notifying** the people involved, and
**recording the audit trail**. Flagging a **possible duplicate** extends reporting: it happens only when a
similar open incident exists. The scheduler's two jobs also notify people and write audit records.
