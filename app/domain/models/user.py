from abc import ABC, abstractmethod

from app.domain.business_rules import BusinessRules
from app.domain.enums import AdminLevel, Role
from app.domain.models._entity import Entity
from app.domain.models._validation import (
    optional_text, require_instance, require_int_min, require_text,
)
from app.domain.exceptions import InvalidInputError


class User(Entity, ABC):
    def __init__(self, username: str, full_name: str, email: str, password_hash: str,
                 role: Role, *, id: int | None = None, active: bool = True):
        super().__init__(id)
        self._username = require_text(username, "username")
        self._full_name = require_text(full_name, "full_name")
        self._email = require_text(email, "email")
        self._password_hash = require_text(password_hash, "password_hash")
        self._role = require_instance(role, Role, "role")
        self._active = bool(active)

    @staticmethod
    def system() -> "User":
        """The actor used for automated actions (classification, scheduler jobs)."""
        return _SYSTEM_USER

    @property
    def username(self) -> str: return self._username
    @property
    def full_name(self) -> str: return self._full_name
    @property
    def email(self) -> str: return self._email
    @property
    def password_hash(self) -> str: return self._password_hash
    @property
    def role(self) -> Role: return self._role
    @property
    def active(self) -> bool: return self._active
    @property
    def is_system(self) -> bool: return False

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @abstractmethod
    def describe(self) -> str:
        """Short human-readable summary, e.g. for logs."""

    def _key(self) -> tuple:
        return (self._id, self._username, self._full_name, self._email,
                self._password_hash, self._role, self._active)

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._username))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._id}, username={self._username!r})"


class Employee(User):
    def __init__(self, username: str, full_name: str, email: str, password_hash: str,
                 department: str = "", *, id: int | None = None, active: bool = True):
        super().__init__(username, full_name, email, password_hash, Role.EMPLOYEE,
                         id=id, active=active)
        self._department = optional_text(department, "department")

    @property
    def department(self) -> str: return self._department

    def describe(self) -> str:
        return f"Employee {self._full_name}" + (f" ({self._department})" if self._department else "")

    def _key(self) -> tuple:
        return super()._key() + (self._department,)


class Technician(User):
    def __init__(self, username: str, full_name: str, email: str, password_hash: str,
                 skills=(), experience_years: int = 0, available: bool = True,
                 max_workload: int = BusinessRules.MAX_ACTIVE_INCIDENTS,
                 *, id: int | None = None, active: bool = True):
        super().__init__(username, full_name, email, password_hash, Role.TECHNICIAN,
                         id=id, active=active)
        if isinstance(skills, str):
            raise InvalidInputError("skills must be a collection of skill names", "skills")
        self._skills = frozenset(require_text(s, "skills") for s in skills)
        self._experience_years = require_int_min(experience_years, 0, "experience_years")
        self._available = bool(available)
        self._max_workload = require_int_min(max_workload, 1, "max_workload")

    @property
    def skills(self) -> frozenset[str]: return self._skills
    @property
    def experience_years(self) -> int: return self._experience_years
    @property
    def available(self) -> bool: return self._available
    @property
    def max_workload(self) -> int: return self._max_workload

    def set_available(self, available: bool) -> None:
        self._available = bool(available)

    def describe(self) -> str:
        return f"Technician {self._full_name}"

    def _key(self) -> tuple:
        return super()._key() + (self._skills, self._experience_years,
                                 self._available, self._max_workload)


class Administrator(User):
    def __init__(self, username: str, full_name: str, email: str, password_hash: str,
                 admin_level: AdminLevel, *, id: int | None = None, active: bool = True):
        super().__init__(username, full_name, email, password_hash, Role.ADMINISTRATOR,
                         id=id, active=active)
        self._admin_level = require_instance(admin_level, AdminLevel, "admin_level")

    @property
    def admin_level(self) -> AdminLevel: return self._admin_level

    def describe(self) -> str:
        return f"Administrator {self._full_name} ({self._admin_level.name})"

    def _key(self) -> tuple:
        return super()._key() + (self._admin_level,)


class SystemUser(User):
    """Special actor: id 0, never stored, cannot log in (hash is not a valid bcrypt hash)."""

    def __init__(self):
        super().__init__("system", "System", "system@iitsm.local", "!", Role.ADMINISTRATOR,
                         id=0, active=True)

    @property
    def is_system(self) -> bool: return True

    def describe(self) -> str:
        return "System"


_SYSTEM_USER = SystemUser()
