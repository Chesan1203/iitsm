"""Keeps the whole test run away from the real data folder.

`app/main.py` builds an app when it is imported (`app = create_app()`), and in real mode that
creates a database, seeds demo data and starts the scheduler. These settings are applied before
any test module imports it, so importing `app.main` in a test only touches a throwaway folder.
Tests that need other settings pass an explicit `Settings(...)`.
"""
import os
import tempfile

_scratch = tempfile.mkdtemp(prefix="iitsm-tests-")
os.environ["DATABASE_PATH"] = os.path.join(_scratch, "iitsm.db")
os.environ["EMAIL_LOG_PATH"] = os.path.join(_scratch, "emails.log")
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["SEED_DEMO_DATA"] = "false"
