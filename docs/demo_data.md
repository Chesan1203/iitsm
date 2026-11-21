# Demo data

`DemoDataSeeder` (`app/persistence/seeder.py`) fills an empty database. Run it alone with
`python -m app.persistence.seeder`, or let `build_real_container` call `seed_if_empty()`.
It does nothing if the database already has users. To start over, delete `data/iitsm.db`.

Every date is relative to "now", so SLA states look right whenever the app starts.
Priorities and SLA status are produced by the real domain engines, not typed in by hand.

## Logins (password for everyone: `Password@123`)

| Role | Usernames | Notes |
| --- | --- | --- |
| Administrator | `admin1` (TEAM_LEAD), `admin2` (SYSTEM_ADMIN), `admin3` (IT_MANAGER), `admin4` (SYSTEM_ADMIN) | Escalation targets follow these levels |
| Technician | `tech1` Ravi Kumar (Database, Storage, Application); `tech2` Priya Menon (Network, Security); `tech3` Arjun Das (Application, Software); `tech4` Neha Kapoor (Authentication, Security); `tech5` Sanjay Patil (Hardware, Storage); `tech6` Lakshmi Rao (Cloud, Network, Database) | `tech6` is unavailable (on leave) and is the only Cloud technician |
| Employee | `emp1` to `emp10` | Spread over Finance, Marketing, HR, Sales, Operations, Legal |

## Reference data

- 8 services: Payment, Database, Network, Authentication (high criticality), Cloud Storage, ERP, VPN (medium), Email (low).
- 9 categories: Hardware, Software, Network, Database, Cloud, Security, Authentication, Application, Storage (the required skill has the same name).
- 2 SLA policies: **Default** (P1 5/30 min, P2 15/120, P3 60/480, P4 240/1440) and **Critical Services** (P1 3/20, P2 10/90, P3 30/360, P4 120/720), which the Payment service uses.

## Incidents: 45 over the last 14 days

21 CLOSED, 3 VERIFIED, 4 RESOLVED, 8 IN_PROGRESS, 3 ACKNOWLEDGED, 4 ASSIGNED, 2 CLASSIFIED.
All four priorities appear. Each has a full audit trail; closed ones include notes, a resolution
and (about half) feedback. 34 in-app notifications exist, the older ones already read.

## Planted for the three demo workflows

| Scenario | What to look at |
| --- | --- |
| **Duplicates** | "Payment application unavailable", "Payment transaction failing" and "Unable to make payment" (all on Payment, opened over the last 90 minutes). The second and third are flagged as possible duplicates of the first. Submitting a new "Payment page is down" incident on the Payment service matches all three. |
| **Correlation** | Three open Network incidents created within the last 40 minutes ("Network outage in building A", "Cannot reach internal websites from floor 2", "Wifi keeps dropping on third floor") form a probable service-level problem. |
| **Escalation** | "Primary database cluster unreachable" is a P1, assigned one minute ago and not acknowledged. Its response deadline is 5 minutes after creation. Advance the demo clock about 4 minutes and run the escalation check: it goes to TEAM_LEAD, then SYSTEM_ADMIN 10 minutes later, then IT_MANAGER. |
| **SLA violations** | The Payment incidents and several others are already violated. "Primary mail server queue growing" sits in its warning zone. |
| **No free technician** | The two Cloud incidents stay CLASSIFIED because the only Cloud technician is unavailable. An administrator can assign them manually. |
