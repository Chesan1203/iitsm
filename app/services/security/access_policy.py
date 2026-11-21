"""Who may see or do what, in one place (role-based authorization).

Service methods call these themselves; the web layer checks again at its boundary, but the
service layer never relies on that.
"""
from __future__ import annotations

from dataclasses import replace

from app.domain.enums import Role
from app.domain.exceptions import UnauthorizedOperationError
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.ports.dto import IncidentSearchCriteria


class AccessPolicy:
    def require_user(self, actor) -> User:
        """The actor must be a real signed-in, active user (not None, not the system actor)."""
        if not isinstance(actor, User) or actor.is_system or actor.id is None:
            raise UnauthorizedOperationError("You must be signed in to do this")
        if not actor.active:
            raise UnauthorizedOperationError("This account is deactivated")
        return actor

    def require_role(self, actor, *roles: Role) -> User:
        user = self.require_user(actor)
        if user.role not in roles:
            allowed = " or ".join(r.name.lower() for r in roles)
            raise UnauthorizedOperationError(f"This action requires the {allowed} role")
        return user

    def is_administrator(self, actor: User) -> bool:
        return actor.role is Role.ADMINISTRATOR

    def can_view(self, actor: User, incident: Incident) -> bool:
        if actor.role is Role.ADMINISTRATOR:
            return True
        if incident.reporter.id == actor.id:
            return True
        tech = incident.assigned_technician
        return actor.role is Role.TECHNICIAN and tech is not None and tech.id == actor.id

    def require_can_view(self, actor, incident: Incident) -> User:
        user = self.require_user(actor)
        if not self.can_view(user, incident):
            raise UnauthorizedOperationError("You are not allowed to view this incident")
        return user

    def scope_criteria(self, actor, criteria: IncidentSearchCriteria) -> IncidentSearchCriteria:
        """A copy of the search criteria limited to what the actor may see: employees only
        their own incidents, technicians only those assigned to them, administrators anything.
        A conflicting filter (for example another reporter) is overridden, not honoured."""
        user = self.require_user(actor)
        if user.role is Role.EMPLOYEE:
            return replace(criteria, reporter_id=user.id)
        if user.role is Role.TECHNICIAN:
            return replace(criteria, technician_id=user.id)
        return criteria
