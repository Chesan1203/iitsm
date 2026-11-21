from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from app.domain.enums import Priority, Role
from app.domain.exceptions import (
    CategoryNotFoundError, InvalidInputError, PersistenceError, ServiceNotFoundError,
    UserNotFoundError,
)
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.user import Technician, User
from app.domain.time_provider import SimulatedTimeProvider, TimeProvider
from app.ports.dto import CategoryRequest, CreateUserRequest, ServiceRequest, SlaPolicyRequest
from app.ports.repositories import (
    CategoryRepository, ServiceRepository, SlaPolicyRepository, UserRepository,
)
from app.ports.services import AdminService
from app.services.impl.strategy_registry import StrategyRegistry
from app.services.impl.user_factory import UserFactory
from app.services.security.access_policy import AccessPolicy


def _clean(text) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


class AdminServiceImpl(AdminService):
    """Every method starts by checking that the actor is a (human) administrator."""

    def __init__(self, users: UserRepository, services: ServiceRepository,
                 categories: CategoryRepository, policies: SlaPolicyRepository,
                 user_factory: UserFactory, priority_strategies: StrategyRegistry,
                 assignment_strategies: StrategyRegistry, time_provider: TimeProvider,
                 access: AccessPolicy, run_sla_check: Callable[[], int],
                 run_escalation_check: Callable[[], int]):
        self._users, self._services, self._categories = users, services, categories
        self._policies, self._factory = policies, user_factory
        self._priority, self._assignment = priority_strategies, assignment_strategies
        self._time, self._access = time_provider, access
        self._run_sla, self._run_escalation = run_sla_check, run_escalation_check

    def _admin(self, actor) -> User:
        return self._access.require_role(actor, Role.ADMINISTRATOR)

    # ---- users ------------------------------------------------------------------------------
    def list_users(self, actor: User) -> list[User]:
        self._admin(actor)
        return self._users.find_all()

    def create_user(self, actor: User, request: CreateUserRequest) -> User:
        self._admin(actor)
        user = self._factory.create(request)
        if self._users.find_by_username(user.username) is not None:
            raise InvalidInputError("That username is already taken", "username")
        try:
            return self._users.save(user)
        except PersistenceError:
            if self._users.find_by_username(user.username) is not None:
                raise InvalidInputError("That username is already taken", "username") from None
            raise

    def deactivate_user(self, actor: User, user_id: int) -> User:
        admin = self._admin(actor)
        if admin.id == user_id:
            raise InvalidInputError("You cannot deactivate your own account", "user_id")
        return self._set_active(user_id, False)

    def activate_user(self, actor: User, user_id: int) -> User:
        self._admin(actor)
        return self._set_active(user_id, True)

    def _set_active(self, user_id: int, active: bool) -> User:
        """Users are deactivated, never deleted: their history must stay readable."""
        user = self._load_user(user_id)
        user.activate() if active else user.deactivate()
        return self._users.save(user)

    def set_technician_availability(self, actor: User, user_id: int, available: bool) -> User:
        self._admin(actor)
        user = self._load_user(user_id)
        if not isinstance(user, Technician):
            raise InvalidInputError("Only technicians have an availability", "user_id")
        user.set_available(available)
        return self._users.save(user)

    def _load_user(self, user_id: int) -> User:
        user = self._users.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")
        return user

    # ---- IT services ---------------------------------------------------------------------------
    def list_services(self, actor: User) -> list[ITService]:
        self._admin(actor)
        return self._services.find_all()

    def create_service(self, actor: User, request: ServiceRequest) -> ITService:
        self._admin(actor)
        service = self._build_service(request, None)
        if self._services.exists_by_name(service.name):
            raise InvalidInputError(f"A service named '{service.name}' already exists", "name")
        return self._save_unique(self._services.save, service, "name")

    def update_service(self, actor: User, id: int, request: ServiceRequest) -> ITService:
        self._admin(actor)
        if self._services.find_by_id(id) is None:
            raise ServiceNotFoundError(f"Service {id} was not found")
        service = self._build_service(request, id)
        if any(s.id != id and s.name.casefold() == service.name.casefold()
               for s in self._services.find_all()):
            raise InvalidInputError(f"A service named '{service.name}' already exists", "name")
        return self._save_unique(self._services.save, service, "name")

    def _build_service(self, request: ServiceRequest, id: int | None) -> ITService:
        if request.sla_policy_id is not None and self._policies.find_by_id(request.sla_policy_id) is None:
            raise InvalidInputError("The chosen SLA policy does not exist", "sla_policy_id")
        return ITService(_clean(request.name), _clean(request.description), request.business_criticality,
                         request.sla_policy_id, request.active, id=id)

    # ---- categories -------------------------------------------------------------------------------
    def list_categories(self, actor: User) -> list[Category]:
        self._admin(actor)
        return self._categories.find_all()

    def create_category(self, actor: User, request: CategoryRequest) -> Category:
        self._admin(actor)
        category = self._build_category(request, None)
        if any(c.name.casefold() == category.name.casefold() for c in self._categories.find_all()):
            raise InvalidInputError(f"A category named '{category.name}' already exists", "name")
        return self._save_unique(self._categories.save, category, "name")

    def update_category(self, actor: User, id: int, request: CategoryRequest) -> Category:
        self._admin(actor)
        if self._categories.find_by_id(id) is None:
            raise CategoryNotFoundError(f"Category {id} was not found")
        category = self._build_category(request, id)
        if any(c.id != id and c.name.casefold() == category.name.casefold()
               for c in self._categories.find_all()):
            raise InvalidInputError(f"A category named '{category.name}' already exists", "name")
        return self._save_unique(self._categories.save, category, "name")

    @staticmethod
    def _build_category(request: CategoryRequest, id: int | None) -> Category:
        return Category(_clean(request.name), _clean(request.description),
                        _clean(request.required_skill), request.active, id=id)

    @staticmethod
    def _save_unique(save, item, field: str):
        """The pre-check above can lose a race; the database's unique rule is the final word."""
        try:
            return save(item)
        except PersistenceError as exc:
            if "UNIQUE" in exc.message.upper():
                raise InvalidInputError(f"That {field} is already in use", field) from None
            raise

    # ---- SLA policies -----------------------------------------------------------------------------
    def list_sla_policies(self, actor: User) -> list[SlaPolicy]:
        self._admin(actor)
        return self._policies.find_all()

    def save_sla_policy(self, actor: User, request: SlaPolicyRequest) -> SlaPolicy:
        """Creates the policy, or updates the existing one with the same name. All four
        priorities are required, and exactly one policy is the default at any time."""
        self._admin(actor)
        name = _clean(request.name)
        targets = self._build_targets(request.targets)
        existing = next((p for p in self._policies.find_all() if p.name.casefold() == name.casefold()), None)
        current_default = self._policies.find_default()
        if not request.is_default and (current_default is None
                                       or (existing is not None and existing.id == current_default.id)):
            raise InvalidInputError(
                "There must always be one default policy: make another policy the default first",
                "is_default")
        saved = self._policies.save(SlaPolicy(name, request.is_default, targets,
                                              id=None if existing is None else existing.id))
        if request.is_default and current_default is not None and current_default.id != saved.id:
            self._policies.save(SlaPolicy(current_default.name, False, current_default.targets,
                                          id=current_default.id))
        return saved

    @staticmethod
    def _build_targets(raw: dict) -> dict[Priority, SlaTarget]:
        missing = [p.name for p in Priority if p not in (raw or {})]
        if missing:
            raise InvalidInputError(
                f"An SLA policy needs a target for every priority; missing {', '.join(missing)}", "targets")
        targets = {}
        for priority in Priority:
            pair = raw[priority]
            try:
                response, resolution = pair
            except (TypeError, ValueError):
                raise InvalidInputError(f"Targets for {priority.name} must be (response, resolution) minutes",
                                        "targets") from None
            if isinstance(response, bool) or isinstance(resolution, bool) or not all(
                    isinstance(v, int) for v in (response, resolution)):
                raise InvalidInputError(f"Targets for {priority.name} must be whole minutes", "targets")
            if response > resolution:
                raise InvalidInputError(
                    f"{priority.name}: the response target cannot be longer than the resolution target", "targets")
            targets[priority] = SlaTarget(response, resolution)
        return targets

    # ---- strategies -------------------------------------------------------------------------------
    def list_assignment_strategies(self, actor: User) -> list[str]:
        self._admin(actor)
        return self._assignment.names()

    def get_assignment_strategy(self, actor: User) -> str:
        self._admin(actor)
        return self._assignment.active_name()

    def set_assignment_strategy(self, actor: User, name: str) -> None:
        self._admin(actor)
        self._assignment.set_active(name)

    def list_priority_strategies(self, actor: User) -> list[str]:
        self._admin(actor)
        return self._priority.names()

    def get_priority_strategy(self, actor: User) -> str:
        self._admin(actor)
        return self._priority.active_name()

    def set_priority_strategy(self, actor: User, name: str) -> None:
        self._admin(actor)
        self._priority.set_active(name)

    # ---- demo clock and manual job runs --------------------------------------------------------------
    def is_time_simulated(self, actor: User) -> bool:
        self._admin(actor)
        return isinstance(self._time, SimulatedTimeProvider)

    def get_current_time(self, actor: User) -> datetime:
        self._admin(actor)
        return self._time.now()

    def advance_time(self, actor: User, minutes: int) -> datetime:
        self._admin(actor)
        clock = self._simulated_clock()
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
            raise InvalidInputError("Minutes must be a whole number of at least 1", "minutes")
        clock.advance(timedelta(minutes=minutes))
        return clock.now()

    def reset_time(self, actor: User) -> datetime:
        self._admin(actor)
        clock = self._simulated_clock()
        clock.reset()
        return clock.now()

    def _simulated_clock(self) -> SimulatedTimeProvider:
        if not isinstance(self._time, SimulatedTimeProvider):
            raise InvalidInputError("The demo clock is only available when the app runs with simulated time")
        return self._time

    def run_sla_check_now(self, actor: User) -> int:
        self._admin(actor)
        return self._run_sla()

    def run_escalation_check_now(self, actor: User) -> int:
        self._admin(actor)
        return self._run_escalation()
