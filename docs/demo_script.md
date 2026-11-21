# Demo and video script

The brief asks for a recorded video of **15 to 20 minutes** in which **every member appears, introduces
themselves and explains a module**, showing **at least three complete workflows**. Upload it, and the
report, to the shared folder the instructor provides.

**File name:** the brief's example is `1_OOP_S1_2025-2026_Project`, which looks like last year's. This year's
file says 2026-2027, so **confirm the exact format with the instructor** before uploading.

## 1. How time works in this demo (read this first)

The demo data are dated **relative to the moment the app first starts**, and the system's clock is the real
clock plus an offset that the administrator can move forward (Demo controls). That has two consequences:

- **Real minutes keep passing while you record.** The planted P1 ("Primary database cluster unreachable") was
  assigned a minute before the app started and its response deadline is 5 minutes after it was created. About
  3 minutes after a fresh start it is already overdue, and if the scheduler is on it escalates on its own.
- **The "related incidents" view looks at the last hour by the current (simulated) time.** The three seeded
  Network incidents were created 13 to 40 minutes before the start. Moving the clock forward by 25 minutes
  or more pushes them out of the window and the "probable service problem" disappears.

So: **record each workflow as its own segment, starting from a fresh database**, and follow the order given
for workflow 3. Segments are joined in an editor afterwards, which is what the plan expects anyway.

## 2. Preparation for every segment

1. **Reset to a fresh database.** Stop the app, delete the database, start again:

   ```bash
   Remove-Item data\iitsm.db*
   .\.venv\Scripts\python.exe -m uvicorn app.main:app
   ```

   (macOS or Linux: `rm data/iitsm.db*`.) The first start takes a few seconds to create the demo data.
2. **Switch the scheduler off while recording** so nothing happens until you press a button:

   ```bash
   $env:ENABLE_SCHEDULER = "false"
   ```

   (macOS or Linux: `export ENABLE_SCHEDULER=false`.) Run this in the terminal before starting the app. Say in
   the video that the same checks run on their own every 30 seconds in normal use.
3. **Open three browser windows or profiles** (employee, technician, administrator) so you can switch roles
   without signing out and in. Every password is `Password@123`.
4. Open `logs/emails.log` in an editor so you can show the simulated emails.
5. **Rehearse each segment twice**, each time from a fresh database, and time it.

### Technician usernames

| Name | Username | Skills |
| --- | --- | --- |
| Ravi Kumar | `tech1` | Database, Storage, Application |
| Priya Menon | `tech2` | Network, Security |
| Arjun Das | `tech3` | Application, Software |
| Neha Kapoor | `tech4` | Authentication, Security |
| Sanjay Patil | `tech5` | Hardware, Storage |

## 3. Running order (about 18 minutes)

| Minutes | Segment | Who |
| --- | --- | --- |
| 0 to 2 | Introductions, the problem, the architecture diagram (`docs/architecture.md`) | P4 leads, everyone says a line |
| 2 to 5 | P1's pre-recorded clip: tests passing, the state machine including the failed NEW to CLOSED jump, a strategy swap, the duplicate detector | P1 |
| 5 to 9 | **Workflow 1:** employee reports; the system prioritises, assigns and notifies | P4 and P3 |
| 9 to 13 | **Workflow 2:** technician investigates; SLA monitored; resolved; user notified; audit trail | P3 and P2 |
| 13 to 17 | **Workflow 3:** correlation, escalation, duplicates | P2 and P4 |
| 17 to 18 | Admin extras: switch strategy, recommend technician, search filters, wrap-up | everyone |

## 4. Workflow 1: employee reports, the system prioritises, assigns and notifies

**Say:** "An employee reports that the payment application is down. Watch what the system does without any
human effort."

1. Sign in as **`emp1`**. Click **Report an incident**.
2. Fill in: Title **"Payment page is down"**, Description **"Customers get an error at checkout and cannot
   pay."**, Service **Payment**, Category **Application**, Impact **High**, Urgency **High**, People affected
   **120**. Submit.
3. **Point out the confirmation message:** priority **P1 (Critical)**, score **27** (impact 3 x urgency 3 x
   service criticality 3), the **response and resolution deadlines** (Payment has a stricter SLA policy, so 3
   and 20 minutes), who it was **assigned** to, and the **possible duplicate** warning (the seeded payment
   incidents are similar).
4. Show the incident page: the eight-step progress bar, the SLA card, and the **timeline** built from the audit
   trail (Created, Duplicate flagged, Classified, Assigned).
5. Note the technician's name on the page and **sign in as that technician** (see the table above). Show the
   **Alerts** count in the top bar, open **Notifications**, and open the incident, which is now in their workload.
6. Show **`logs/emails.log`**: the simulated email to the reporter and the technician. **Explain:** two
   notification mechanisms, in-app and simulated email; a third would be one new class.

## 5. Workflow 2: investigate, monitor the SLA, resolve, notify, audit

Start this segment from a fresh database, then repeat step 1 to 2 of workflow 1 quickly to create an incident.
**Say:** "The technician works the incident while the system watches the deadlines."

1. As the **technician**: open the incident, press **Acknowledge**, then **Start investigation**, then add a
   note, for example "Reproduced on the test environment". Press **Request information** with the question
   "Since when?".
2. As **`emp1`**: the incident page now has a **reply box** with the question. Answer it.
3. As **`admin1`**: open **Demo controls**. Show that simulated time is on. Press **+15 minutes**, then **Run
   SLA check now**. Payment's resolution window is 20 minutes, and 80 percent of it is 16 minutes, so with a
   few real minutes already elapsed a **warning** should appear. Press **+5 minutes** and run the check again
   for a **violation**. *Which event you get first depends on the real time that has passed, so rehearse this and
   note it;* either one demonstrates the monitor. Open the incident to show the **SLA status** change, and
   **SLA violations** to show the list.
4. As the **technician**: press **Resolve**, with a summary and details.
5. As **`emp1`**: the notification arrives; open the incident, **Verify** the fix, **Close** it, and give
   **feedback** (rating and comment).
6. As **admin**: open the incident and show the **timeline**, or **Audit log** filtered to this incident,
   listing every step with who did it and when. **Explain:** the audit trail is written by an observer that
   listens to the incident's events, so no step can be forgotten.

## 6. Workflow 3: correlation, escalation, duplicates

**Start this segment from a fresh database and begin immediately** (within about two minutes of starting the
app). The order below matters because of how time works (section 1).

**Part A: correlation (before touching the clock)**

1. As **`admin1`**, open **Reports** and scroll to **Related incidents**: three open **Network** incidents form
   a **"Probable service problem"**. **Explain** correlation: three or more open incidents on one service in
   the last hour.

**Part B: escalation**

2. Open **Demo controls**. Press **Run escalation check now**: **0 escalated**, because the planted P1's response
   deadline has not passed yet. (If it says 1, more than about three minutes have passed since the app started;
   reset and start again.)
3. Press **+5 minutes**, then **Run escalation check now**: **1 escalated**, to **Team lead**. Open the incident
   ("Primary database cluster unreachable", found through **All incidents**): the Escalation field shows the
   new level, and the timeline shows the escalation.
4. Press **+5 minutes** twice (10 minutes), run the check: **System admin**. Press **+5 minutes** twice again,
   run the check: **IT manager**. Run it once more: **0 escalated** (IT manager is the top).
5. Sign in as **`admin3`** (the IT manager) and open **Notifications** to show the escalation notices, and show
   the **Audit log** filtered to the action **Escalated**. **Explain:** one level up every 10 minutes of being
   overdue, capped at IT manager, and only for a P1 nobody has acknowledged.

**Part C: duplicates (not affected by the clock)**

6. As **`emp2`** and then **`emp3`**, report two more payment incidents with different wording, for example
   "Payment transaction failing" and "Unable to make payment" (service Payment, category Application, any
   description). Show the **possible duplicate** flag on each, with the earlier ticket named. **Explain** the
   method: lower-case, remove stop words, map synonyms such as *unavailable / down / failing*, compare the word
   sets, add a bonus for the same service, flag at 0.5 or more. It flags and never merges.

## 7. Admin extras (about one minute)

- **Strategies:** open **Strategies**, switch assignment from *Skill based* to *Load based*, report one more
  incident and show that it goes to the least loaded technician. **Explain:** the Strategy pattern, swapped with
  no restart.
- **Recommend technician:** on an incident, press **Recommend technician** to show the ranked list with scores
  and reasons.
- **Search:** open **All incidents** and use several filters (status, priority, service, keyword, dates).
- **Close:** each member says one sentence about what they built.

## 8. What each person should be ready to explain on camera

| Person | Module | Points to explain |
| --- | --- | --- |
| P1 | Domain | State pattern and why NEW to CLOSED is impossible; priority and assignment strategies; SLA engine; duplicate detection; escalation rule |
| P2 | Persistence | Repository pattern; schema and constraints; why SQLite; seed data; the report queries |
| P3 | Services | Composition root; observers (audit and notifications); channels; the scheduler and the once-only rule; security |
| P4 | Web | Role-based pages and guards; the incident page and which buttons appear and why; error handling; stub mode |

## 9. Recording tips

- Record each person's segment separately (OBS Studio is free, or use the computer's screen recorder) and join
  the clips with any simple editor.
- Use a browser zoom of 110 to 125 percent so the text is readable.
- If the pages look unstyled, the browser has no internet access: they load Bootstrap from a CDN.
- Keep the terminal with the server out of the shot; it logs very little.
