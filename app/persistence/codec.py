"""The one place that converts between Python values and what SQLite stores.

Dates are ISO text, booleans are 0/1, enums are stored by NAME (Level by its number).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import TypeVar

from app.domain.enums import Level
from app.domain.exceptions import PersistenceError

E = TypeVar("E", bound=Enum)


def dt_to_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(sep=" ")


def dt_from_text(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def day_start_text(day: date) -> str:
    """Text for 00:00:00 on `day`; use with `>=` for an inclusive start date."""
    return dt_to_text(datetime.combine(_as_date(day), time.min))


def next_day_start_text(day: date) -> str:
    """Text for 00:00:00 on the day after `day`; use with `<` for an inclusive end date."""
    return dt_to_text(datetime.combine(_as_date(day) + timedelta(days=1), time.min))


def _as_date(day: date) -> date:
    return day.date() if isinstance(day, datetime) else day


def flag(value: bool | None) -> int | None:
    return None if value is None else int(bool(value))


def enum_to_text(member: Enum | None) -> str | None:
    return None if member is None else member.name


def enum_from_text(enum_class: type[E], text: str | None) -> E | None:
    if text is None:
        return None
    try:
        return enum_class[text]
    except KeyError:
        raise PersistenceError(f"Stored value {text!r} is not a valid {enum_class.__name__}") from None


def level_to_int(level: Level) -> int:
    return level.value


def level_from_int(number: int) -> Level:
    try:
        return Level(number)
    except ValueError:
        raise PersistenceError(f"Stored value {number!r} is not a valid Level") from None


def placeholders(count: int) -> str:
    """'?, ?, ?' for an IN (...) list. Only question marks are ever joined into SQL text."""
    return ", ".join("?" * count)
