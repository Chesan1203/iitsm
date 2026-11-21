# Running the project

Requires **Python 3.11 or newer** and Git. Everything below is run from the repository root.

## 1. First-time setup

Windows (PowerShell):

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The commands below call the virtual environment's Python directly (`.\.venv\Scripts\python.exe` on
Windows, `.venv/bin/python` elsewhere), so you never have to "activate" it. If you prefer to activate
it, use `.\.venv\Scripts\Activate.ps1` (Windows; if PowerShell refuses, run
`Set-ExecutionPolicy -Scope Process RemoteSigned` first) or `source .venv/bin/activate`.

## 2. Run the tests

```bash
.\.venv\Scripts\python.exe -m pytest
```

All tests should pass (815 at the time of writing, in roughly a minute). The tests never touch the real
`data/` folder.

## 3. Start the application

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> and sign in (section 4). `/health` answers `{"status":"ok","mode":"real"}`,
which is handy for checking that the server is up.

On the very first start, with no database yet, the app:
1. creates the `data/` folder and `data/iitsm.db`;
2. fills it with demo data (a few seconds);
3. starts the background scheduler.

Later starts skip step 2 because the database already has users. **The internet is needed in the browser**:
the pages load Bootstrap from a CDN.

### What you will find

| Role | Pages |
| --- | --- |
| Everyone | Sign in, register (employees), notifications, incident page, search |
| Employee | My incidents, report an incident |
| Technician | My work (workload and assigned incidents), the action buttons on an incident |
| Administrator | Dashboard, all incidents and search, users, services, categories, SLA policies, strategies, reports, audit log, SLA violations, demo controls |

### Stub mode (the web layer without the real services)

Stub mode runs the same pages against in-memory sample data: no database, no scheduler, nothing saved, and
restarting resets everything. It is for working on the pages and for tests.

```bash
$env:ITSM_MODE = "stub"      # Windows PowerShell;  macOS/Linux: export ITSM_MODE=stub
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Stub logins (password `Password@123`): `emp1` to `emp3`, `tech1` to `tech3`, `admin1` to `admin3`.
Incident 999 refuses every action, which is useful for seeing how errors are shown. In stub mode the demo
clock moves forward but no real checks run: "Run SLA check" and "Run escalation check" only count the
incidents that are due.

## 4. Demo logins (real mode)

Every seeded user has the password **`Password@123`**.

| Role | Usernames |
| --- | --- |
| Administrator | `admin1` (team lead), `admin2` and `admin4` (system admin), `admin3` (IT manager) |
| Technician | `tech1` to `tech6` (`tech6` is on leave) |
| Employee | `emp1` to `emp10` |

`docs/demo_data.md` lists the technicians' names and skills, the services, and the planted demo scenarios
(duplicates, a correlated Network problem, an escalating P1, SLA violations).

## 5. Settings (environment variables)

All optional. Set them in the same terminal before starting the app.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ITSM_MODE` | `real` | `real` for the real services, `stub` for the in-memory sample data |
| `DATABASE_PATH` | `data/iitsm.db` | The SQLite file |
| `EMAIL_LOG_PATH` | `logs/emails.log` | Where simulated emails are written |
| `SECRET_KEY` | `dev-only-change-me` | Signs the session cookie. Set a long random value for anything but a demo. |
| `SIMULATED_TIME` | `true` | Enables the demo clock controls for administrators |
| `SEED_DEMO_DATA` | `true` | Fill an empty database with demo data on start |
| `ENABLE_SCHEDULER` | `true` | Run the SLA and escalation checks every 30 seconds |

## 6. Useful tasks

**Start again with fresh demo data.** Stop the app, delete the database, start the app:

```bash
Remove-Item data\iitsm.db*
```

(`rm data/iitsm.db*` on macOS or Linux.) The `*` also removes the `-wal` and `-shm` helper files.

**Seed without starting the app:**

```bash
.\.venv\Scripts\python.exe -m app.persistence.seeder
```

**See the simulated emails.** Every notification is also written as a readable block to
`logs/emails.log` (To, Subject, Body).

**Show deadlines, violations and escalation.** Sign in as `admin1`, open **Demo controls**, move the clock
forward (+5, +15, +30 or +60 minutes) and press **Run SLA check now** or **Run escalation check now**; each
reports how many events it produced. The seeded P1 "Primary database cluster unreachable" is created a
minute or two before the first start with a 5-minute response deadline, so with the scheduler on it escalates
by itself about 3 minutes after the first start. It then moves up one level for every 10 minutes it stays
overdue. `docs/demo_script.md` has the full demonstration, including the order to do things in (the demo
clock affects what the "related incidents" report shows).

## 7. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `python` is not recognised, or opens the Microsoft Store | Install Python from python.org (tick "Add python.exe to PATH") or `winget install Python.Python.3.12`, then open a new terminal |
| `ModuleNotFoundError: No module named 'app'` | You are not in the repository root. `cd` to the folder that contains `app/` and `tests/` |
| `ModuleNotFoundError` for `fastapi`, `bcrypt`, ... | Run the install command in section 1 again, using the virtual environment's Python |
| "address already in use" on startup | Another copy is running. Stop it, or add `--port 8001` |
| The pages look unstyled | The browser cannot reach the Bootstrap CDN: check the internet connection |
| Strange data after a schema change | Delete `data/iitsm.db*` and start again (there are no migrations) |
| The first start seems stuck | Seeding takes a few seconds on an empty database; wait for "Application startup complete" |
| You are signed out unexpectedly | Sessions end when the account is deactivated, and after 14 days. Changing `SECRET_KEY` signs everyone out |
