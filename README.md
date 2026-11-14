# I-ITSM: Intelligent IT Service Management & Incident Resolution System

Python 3.11+ / FastAPI / SQLite. OOP course project (CS F213 / MAC F212).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## Run

```bash
uvicorn app.main:app --reload                       # real services (default)
ITSM_MODE=stub uvicorn app.main:app --reload        # stand-in services (UI work)
```

Windows PowerShell: `$env:ITSM_MODE="stub"` before `uvicorn`.

Health check: http://127.0.0.1:8000/health

## Environment variables

`ITSM_MODE` (real|stub), `DATABASE_PATH`, `EMAIL_LOG_PATH`, `SECRET_KEY`, `SIMULATED_TIME`,
`SEED_DEMO_DATA`, `ENABLE_SCHEDULER` (see `app/config.py` for defaults).

## Layout and rules

See `CONTRACT.md`. Import rules are enforced by `tests/test_architecture.py`.

Demo logins and the full run guide are added by P3 at integration (Thu 19 Nov).
