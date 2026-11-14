import pytest

from app.config import Settings


def test_defaults():
    s = Settings.from_env({})
    assert (s.ITSM_MODE, s.SIMULATED_TIME, s.SEED_DEMO_DATA, s.ENABLE_SCHEDULER) == ("real", True, True, True)
    assert s.DATABASE_PATH == "data/iitsm.db"


def test_environment_overrides_and_flag_parsing():
    s = Settings.from_env({"ITSM_MODE": " STUB ", "ENABLE_SCHEDULER": "false", "SIMULATED_TIME": "0",
                           "SEED_DEMO_DATA": "Yes", "DATABASE_PATH": "x.db"})
    assert s.ITSM_MODE == "stub" and not s.ENABLE_SCHEDULER and not s.SIMULATED_TIME
    assert s.SEED_DEMO_DATA and s.DATABASE_PATH == "x.db"


def test_invalid_values_are_rejected():
    with pytest.raises(ValueError):
        Settings.from_env({"ITSM_MODE": "fake"})
    with pytest.raises(ValueError):
        Settings.from_env({"ENABLE_SCHEDULER": "maybe"})
