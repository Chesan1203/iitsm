"""Turning the text of a submitted form into numbers, dates and enum members.

A value that cannot be read becomes None. The service then rejects it with its own message, so
the wording of validation errors stays in one place (the services), not in the routes.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)


def to_int(text: str | None) -> int | None:
    """'12' becomes 12. Anything else (empty, '1.5', '-3', 'abc') becomes None."""
    return int(text.strip()) if text and text.strip().isdigit() else None


def to_date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text.strip()) if text and text.strip() else None
    except ValueError:
        return None


def to_enum(enum_class: type[E], name: str | None) -> E | None:
    """Look an enum member up by its name ('HIGH'). Unknown names become None."""
    return enum_class.__members__.get((name or "").strip())


def field_errors(exc, known_fields) -> dict[str, str]:
    """The error to show on a form, keyed by the field it belongs to.

    A service may report a problem against a field the form does not have (for example a domain
    rule on 'response_minutes'). Such a message goes under the key 'form', which every form
    shows as a general error, so that a message is never silently lost."""
    field = getattr(exc, "field", None)
    return {field if field in known_fields else "form": exc.message}


def to_list(text: str | None) -> tuple[str, ...]:
    """'Network, Cloud ,' becomes ('Network', 'Cloud')."""
    return tuple(part.strip() for part in (text or "").split(",") if part.strip())
