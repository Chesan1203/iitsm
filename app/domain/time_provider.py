from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from app.domain.exceptions import InvalidInputError


class TimeProvider(ABC):
    """The only source of 'now'. Domain logic never reads the clock itself."""

    @abstractmethod
    def now(self) -> datetime: ...


class SystemTimeProvider(TimeProvider):
    def now(self) -> datetime:
        return datetime.now()


class SimulatedTimeProvider(TimeProvider):
    """Real clock plus an offset, so a demo can fast-forward to trigger SLA breaches."""

    def __init__(self):
        self._offset = timedelta(0)

    @property
    def offset(self) -> timedelta:
        return self._offset

    def now(self) -> datetime:
        return datetime.now() + self._offset

    def advance(self, delta: timedelta) -> None:
        if not isinstance(delta, timedelta) or delta < timedelta(0):
            raise InvalidInputError("Time can only be advanced by a positive duration", "minutes")
        self._offset += delta

    def reset(self) -> None:
        self._offset = timedelta(0)
