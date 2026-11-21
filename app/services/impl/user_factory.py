from __future__ import annotations

from app.domain.enums import AdminLevel, Role
from app.domain.exceptions import InvalidInputError
from app.domain.models.user import Administrator, Employee, Technician, User
from app.ports.dto import CreateUserRequest
from app.services.security.input_rules import (
    validate_email, validate_full_name, validate_password, validate_username,
)
from app.services.security.password_hasher import PasswordHasher


class UserFactory:
    """Factory pattern: one place that decides which User subclass to build for a role.
    The password arrives in plain text and leaves already hashed."""

    def __init__(self, hasher: PasswordHasher):
        self._hasher = hasher

    def create(self, request: CreateUserRequest) -> User:
        username = validate_username(request.username)
        full_name = validate_full_name(request.full_name)
        email = validate_email(request.email)
        password_hash = self._hasher.hash(validate_password(request.password))
        role = request.role
        if role is Role.EMPLOYEE:
            return Employee(username, full_name, email, password_hash, request.department or "")
        if role is Role.TECHNICIAN:
            skills = [s.strip() for s in request.skills if isinstance(s, str) and s.strip()]
            return Technician(username, full_name, email, password_hash, skills,
                              request.experience_years, True, request.max_workload)
        if role is Role.ADMINISTRATOR:
            if not isinstance(request.admin_level, AdminLevel):
                raise InvalidInputError("An administrator needs an admin level", "admin_level")
            return Administrator(username, full_name, email, password_hash, request.admin_level)
        raise InvalidInputError("Unknown role", "role")
