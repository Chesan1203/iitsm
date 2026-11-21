from __future__ import annotations

from app.domain.exceptions import UnauthorizedOperationError
from app.domain.models.notification import Notification
from app.domain.models.user import User
from app.ports.repositories import NotificationRepository
from app.ports.services import NotificationService
from app.services.security.access_policy import AccessPolicy

MAX_LIST = 200
_OWNERSHIP_LOOKUP = 1000          # how many recent notifications are searched to prove ownership


class NotificationServiceImpl(NotificationService):
    """A user can only read and mark their own notifications."""

    def __init__(self, notifications: NotificationRepository, access: AccessPolicy):
        self._notifications, self._access = notifications, access

    def list_for_user(self, actor: User, limit: int) -> list[Notification]:
        user = self._access.require_user(actor)
        return self._notifications.find_by_recipient(user.id, max(1, min(int(limit), MAX_LIST)))

    def unread_count(self, actor: User) -> int:
        user = self._access.require_user(actor)
        return self._notifications.count_unread(user.id)

    def mark_read(self, actor: User, notification_id: int) -> None:
        """Marks one of the actor's own notifications. The repository cannot look up a single
        notification, so ownership is proven by finding it among the actor's recent ones. An
        unknown id and someone else's id give the same error, so nothing is revealed."""
        user = self._access.require_user(actor)
        mine = self._notifications.find_by_recipient(user.id, _OWNERSHIP_LOOKUP)
        if not any(n.id == notification_id for n in mine):
            raise UnauthorizedOperationError("You can only mark your own notifications as read")
        self._notifications.mark_read(notification_id)

    def mark_all_read(self, actor: User) -> None:
        user = self._access.require_user(actor)
        self._notifications.mark_all_read(user.id)
