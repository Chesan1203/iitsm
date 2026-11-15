from datetime import datetime

from app.domain.exceptions import InvalidInputError


def _label(field: str) -> str:
    return field.replace("_", " ")


def require_text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{_label(field)} must not be blank", field)
    return value.strip()


def optional_text(value, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidInputError(f"{_label(field)} must be text", field)
    return value.strip()


def require_instance(value, expected, field: str):
    if not isinstance(value, expected):
        raise InvalidInputError(f"{_label(field)} is invalid", field)
    return value


def require_int_min(value, minimum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InvalidInputError(f"{_label(field)} must be a whole number of at least {minimum}", field)
    return value


def require_int_between(value, low: int, high: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidInputError(f"{_label(field)} must be a whole number from {low} to {high}", field)
    return value


def require_naive_datetime(value, field: str) -> datetime:
    """Domain times are local, without a time zone. A zone-aware value would raise an obscure
    TypeError the first time it is compared with a naive one, so it is rejected up front."""
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise InvalidInputError(f"{_label(field)} must be a date and time without a time zone", field)
    return value
