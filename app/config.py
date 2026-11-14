"""Settings read from environment variables. Pure standard library, importable by any layer
except domain and ports."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_MODES = ("real", "stub")


def _flag(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{key} must be one of {sorted(_TRUE | _FALSE)}, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    ITSM_MODE: str = "real"                    # "real" or "stub" (stand-in services for UI work)
    DATABASE_PATH: str = "data/iitsm.db"
    EMAIL_LOG_PATH: str = "logs/emails.log"
    SECRET_KEY: str = "dev-only-change-me"     # signs the session cookie
    SIMULATED_TIME: bool = True                # enables the demo clock controls
    SEED_DEMO_DATA: bool = True
    ENABLE_SCHEDULER: bool = True              # tests switch this off

    def __post_init__(self):
        if self.ITSM_MODE not in _MODES:
            raise ValueError(f"ITSM_MODE must be one of {_MODES}, got {self.ITSM_MODE!r}")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        defaults = cls()
        return cls(
            ITSM_MODE=env.get("ITSM_MODE", defaults.ITSM_MODE).strip().lower(),
            DATABASE_PATH=env.get("DATABASE_PATH", defaults.DATABASE_PATH),
            EMAIL_LOG_PATH=env.get("EMAIL_LOG_PATH", defaults.EMAIL_LOG_PATH),
            SECRET_KEY=env.get("SECRET_KEY", defaults.SECRET_KEY),
            SIMULATED_TIME=_flag(env, "SIMULATED_TIME", defaults.SIMULATED_TIME),
            SEED_DEMO_DATA=_flag(env, "SEED_DEMO_DATA", defaults.SEED_DEMO_DATA),
            ENABLE_SCHEDULER=_flag(env, "ENABLE_SCHEDULER", defaults.ENABLE_SCHEDULER),
        )
