from __future__ import annotations

from app.domain.enums import Role
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.models.user import Technician, User
from app.ports.repositories import CategoryRepository, ServiceRepository, UserRepository
from app.ports.services import LookupService
from app.services.security.access_policy import AccessPolicy


class LookupServiceImpl(LookupService):
    """Read-only lists for dropdowns."""

    def __init__(self, services: ServiceRepository, categories: CategoryRepository,
                 users: UserRepository, access: AccessPolicy):
        self._services, self._categories, self._users, self._access = services, categories, users, access

    def list_active_services(self, actor: User) -> list[ITService]:
        self._access.require_user(actor)
        return [s for s in self._services.find_all() if s.active]

    def list_active_categories(self, actor: User) -> list[Category]:
        self._access.require_user(actor)
        return [c for c in self._categories.find_all() if c.active]

    def list_technicians(self, actor: User) -> list[Technician]:
        """Administrators only (they pick who to assign). Active accounts, available or not,
        so the dropdown can show who is on leave."""
        self._access.require_role(actor, Role.ADMINISTRATOR)
        return [t for t in self._users.find_by_role(Role.TECHNICIAN) if t.active]
