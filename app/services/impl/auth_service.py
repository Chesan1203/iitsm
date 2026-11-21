from __future__ import annotations

import logging

from app.domain.enums import Role
from app.domain.exceptions import InvalidInputError, InvalidLoginError, PersistenceError
from app.domain.models.user import User
from app.ports.dto import CreateUserRequest, RegisterRequest
from app.ports.repositories import UserRepository
from app.ports.services import AuthService
from app.services.impl.user_factory import UserFactory
from app.services.security.password_hasher import PasswordHasher

logger = logging.getLogger(__name__)

_GENERIC_FAILURE = "Invalid username or password"


class AuthServiceImpl(AuthService):
    def __init__(self, users: UserRepository, hasher: PasswordHasher, factory: UserFactory):
        self._users, self._hasher, self._factory = users, hasher, factory
        # Verified against when the username is unknown, so a missing user and a wrong
        # password take about the same time and an attacker cannot tell them apart.
        self._decoy_hash = hasher.hash("decoy-password-for-timing")

    def login(self, username: str, password: str) -> User:
        """Unknown user, wrong password and deactivated account all fail the same way."""
        user = self._users.find_by_username(username.strip()) if isinstance(username, str) else None
        stored = user.password_hash if user is not None else self._decoy_hash
        password_ok = self._hasher.verify(password, stored)
        if user is None or not password_ok or not user.active:
            raise InvalidLoginError(_GENERIC_FAILURE)
        return user

    def register_employee(self, request: RegisterRequest) -> User:
        """Self-registration always creates an Employee, whatever the request says."""
        create = CreateUserRequest(
            username=request.username, full_name=request.full_name, email=request.email,
            password=request.password, role=Role.EMPLOYEE, department=request.department)
        user = self._factory.create(create)               # validates every field first
        if self._users.find_by_username(user.username) is not None:
            raise InvalidInputError("That username is already taken", "username")
        try:
            return self._users.save(user)
        except PersistenceError:
            # Two people registering the same name at once: the database's unique rule wins.
            if self._users.find_by_username(user.username) is not None:
                raise InvalidInputError("That username is already taken", "username") from None
            raise

    def get_user(self, user_id: int) -> User | None:
        """For reloading the logged-in user from the session. A deactivated user is treated
        as not logged in, so deactivation ends their session at the next request."""
        user = self._users.find_by_id(user_id)
        return user if user is not None and user.active else None
