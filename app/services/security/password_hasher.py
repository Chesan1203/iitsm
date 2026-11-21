from __future__ import annotations

import bcrypt

from app.domain.exceptions import InvalidInputError
from app.services.security.input_rules import MAX_PASSWORD_BYTES


class PasswordHasher:
    """bcrypt: a one-way hash with a built-in random salt. The plain password is never stored
    or logged. `rounds` is the work factor (12 is the default; tests use the minimum, 4)."""

    def __init__(self, rounds: int = 12):
        self._rounds = rounds

    def hash(self, plain: str) -> str:
        data = self._encode(plain)
        if len(data) > MAX_PASSWORD_BYTES:
            raise InvalidInputError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes", "password")
        return bcrypt.hashpw(data, bcrypt.gensalt(self._rounds)).decode("ascii")

    def verify(self, plain: str, hashed: str) -> bool:
        """True only if `plain` matches. Never raises: a malformed hash or an over-long
        password simply does not match."""
        if not isinstance(plain, str) or not isinstance(hashed, str):
            return False
        data = plain.encode("utf-8")
        if len(data) > MAX_PASSWORD_BYTES:
            return False
        try:
            return bcrypt.checkpw(data, hashed.encode("ascii"))
        except (ValueError, UnicodeError):                # malformed hash
            return False

    @staticmethod
    def _encode(plain: str) -> bytes:
        if not isinstance(plain, str):
            raise InvalidInputError("Password is required", "password")
        return plain.encode("utf-8")
