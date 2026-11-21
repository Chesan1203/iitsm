from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

from app.domain.exceptions import InvalidInputError
from app.ports.repositories import SettingsRepository


class _Named(Protocol):
    @property
    def name(self) -> str: ...


S = TypeVar("S", bound=_Named)

PRIORITY_SETTING = "priority.strategy"
ASSIGNMENT_SETTING = "assignment.strategy"


class StrategyRegistry(Generic[S]):
    """A dict from strategy name to strategy object, plus which one is active.

    The active name lives in the settings table and is read on EVERY use, so an administrator
    switching strategy takes effect on the next incident with no restart. A missing or
    unknown stored name falls back to the default instead of failing.
    """

    def __init__(self, settings: SettingsRepository, setting_key: str,
                 strategies: Sequence[S], default_name: str):
        self._settings = settings
        self._key = setting_key
        self._by_name: dict[str, S] = {s.name: s for s in strategies}
        if default_name not in self._by_name:
            raise ValueError(f"Default strategy {default_name!r} is not registered")
        self._default = default_name

    def names(self) -> list[str]:
        return list(self._by_name)

    def active_name(self) -> str:
        stored = self._settings.get(self._key)
        return stored if stored in self._by_name else self._default

    def active(self) -> S:
        return self._by_name[self.active_name()]

    def get(self, name: str) -> S:
        try:
            return self._by_name[name]
        except KeyError:
            raise InvalidInputError(
                f"Unknown strategy '{name}'. Choose one of: {', '.join(self._by_name)}", "name") from None

    def set_active(self, name: str) -> None:
        self.get(name)                       # validates
        self._settings.put(self._key, name)
