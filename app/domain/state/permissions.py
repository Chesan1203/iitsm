"""Who may perform an action. Each helper raises UnauthorizedOperationError.

Users are compared by id. `User.system()` has role ADMINISTRATOR, so it passes
require_admin_or_system but not require_admin (human administrators only).
"""
from app.domain.enums import Role
from app.domain.exceptions import UnauthorizedOperationError
from app.domain.models.user import User


def _checked(actor) -> User:
    if not isinstance(actor, User):
        raise UnauthorizedOperationError("You must be signed in to do this")
    return actor


def _same_user(actor: User, other: User | None) -> bool:
    return other is not None and actor.id is not None and actor.id == other.id


def require_system(actor, action: str = "perform this action") -> None:
    if not _checked(actor).is_system:
        raise UnauthorizedOperationError(f"Only the system can {action}")


def require_admin(actor, action: str = "perform this action") -> None:
    actor = _checked(actor)
    if actor.role is not Role.ADMINISTRATOR or actor.is_system:
        raise UnauthorizedOperationError(f"Only an administrator can {action}")


def require_admin_or_system(actor, action: str = "perform this action") -> None:
    if _checked(actor).role is not Role.ADMINISTRATOR:
        raise UnauthorizedOperationError(f"Only an administrator or the system can {action}")


def require_assigned_technician(incident, actor, action: str = "perform this action") -> None:
    if not _same_user(_checked(actor), incident.assigned_technician):
        raise UnauthorizedOperationError(f"Only the assigned technician can {action}")


def require_reporter(incident, actor, action: str = "perform this action") -> None:
    if not _same_user(_checked(actor), incident.reporter):
        raise UnauthorizedOperationError(f"Only the person who reported the incident can {action}")


def require_reporter_or_system(incident, actor, action: str = "perform this action") -> None:
    actor = _checked(actor)
    if not (actor.is_system or _same_user(actor, incident.reporter)):
        raise UnauthorizedOperationError(f"Only the reporter or the system can {action}")


def require_reporter_or_admin(incident, actor, action: str = "perform this action") -> None:
    actor = _checked(actor)
    is_admin = actor.role is Role.ADMINISTRATOR and not actor.is_system
    if not (is_admin or _same_user(actor, incident.reporter)):
        raise UnauthorizedOperationError(f"Only the reporter or an administrator can {action}")
