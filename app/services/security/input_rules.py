"""Validation rules for user input, shared by registration and administrator user creation.

Every failure raises InvalidInputError naming the offending field.
"""
from __future__ import annotations

import re

from app.domain.business_rules import BusinessRules
from app.domain.exceptions import InvalidInputError

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._]{3,30}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_BYTES = 72          # bcrypt ignores (and bcrypt 5 rejects) anything longer
MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 100


def validate_username(username) -> str:
    text = (username or "").strip() if isinstance(username, str) else ""
    if not USERNAME_PATTERN.match(text):
        raise InvalidInputError(
            "Username must be 3 to 30 characters: letters, digits, dot or underscore", "username")
    return text


def validate_password(password) -> str:
    if not isinstance(password, str) or len(password) < BusinessRules.MIN_PASSWORD_LENGTH:
        raise InvalidInputError(
            f"Password must be at least {BusinessRules.MIN_PASSWORD_LENGTH} characters", "password")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise InvalidInputError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes", "password")
    return password


def validate_email(email) -> str:
    text = email.strip() if isinstance(email, str) else ""
    if not text or len(text) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(text):
        raise InvalidInputError("Enter a valid email address", "email")
    return text


def validate_full_name(name) -> str:
    text = " ".join(name.split()) if isinstance(name, str) else ""
    if not text:
        raise InvalidInputError("Full name is required", "full_name")
    if len(text) > MAX_NAME_LENGTH:
        raise InvalidInputError(f"Full name must be at most {MAX_NAME_LENGTH} characters", "full_name")
    return text
