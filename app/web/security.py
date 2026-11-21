"""Who is logged in, and who may open which page.

The logged-in user always comes from the signed session cookie (which stores only the user's id),
never from a form field or a URL. Guards are attached to every router, so typing a URL directly is
blocked just like a hidden menu link.
"""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from fastapi import Depends, Request

from app.domain.enums import Role
from app.domain.exceptions import UnauthorizedOperationError
from app.domain.models.user import User
from app.ports.container import Container

SESSION_KEY = "user_id"

HOME_BY_ROLE = {
    Role.EMPLOYEE: "/employee/dashboard",
    Role.TECHNICIAN: "/tech/dashboard",
    Role.ADMINISTRATOR: "/admin/dashboard",
}


class NotAuthenticated(Exception):
    """Raised by the guards when nobody is logged in. errors.py turns it into a redirect to /login."""


def get_container(request: Request) -> Container:
    return request.app.state.container


def session_user(request: Request) -> User | None:
    """The logged-in user, or None. Reloaded through the auth service on the first call of each
    request, so a user who was deactivated since logging in is logged out immediately."""
    if hasattr(request.state, "user"):
        return request.state.user
    user = None
    user_id = request.session.get(SESSION_KEY)
    if isinstance(user_id, int):
        user = get_container(request).auth.get_user(user_id)
    if user is None and SESSION_KEY in request.session:
        request.session.clear()                      # stale or tampered session
    request.state.user = user
    return user


def get_current_user(request: Request) -> User:
    user = session_user(request)
    if user is None:
        raise NotAuthenticated()
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """A dependency that lets only the given roles through (others get a 403 page)."""
    allowed = set(roles)

    def check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise UnauthorizedOperationError("You do not have access to this page")
        return user
    return check


def home_for(user: User) -> str:
    return HOME_BY_ROLE[user.role]


def safe_next(target: str | None) -> str | None:
    """Only a plain path on this site may be used as a post-login destination, so a crafted
    link cannot send someone to another website after they log in."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parsed = urlparse(target)
    return target if not parsed.scheme and not parsed.netloc else None
