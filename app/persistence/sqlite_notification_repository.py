from __future__ import annotations

import sqlite3
from dataclasses import replace

from app.domain.enums import ChannelType, IncidentEventType
from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.notification import Notification
from app.persistence.codec import dt_from_text, dt_to_text, enum_from_text, flag
from app.persistence.database import Database
from app.ports.repositories import NotificationRepository


def _notification(row: sqlite3.Row) -> Notification:
    try:
        return Notification(
            id=row["id"], recipient_id=row["recipient_id"], incident_id=row["incident_id"],
            event_type=enum_from_text(IncidentEventType, row["event_type"]),
            channel=enum_from_text(ChannelType, row["channel"]), message=row["message"],
            created_at=dt_from_text(row["created_at"]), is_read=bool(row["is_read"]))
    except InvalidInputError as exc:
        raise PersistenceError(f"Stored notification {row['id']} is invalid: {exc}") from exc


class SqliteNotificationRepository(NotificationRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, notification: Notification) -> Notification:
        """Insert when id is None, otherwise update. Returns the saved notification."""
        values = (notification.recipient_id, notification.incident_id,
                  notification.event_type.name, notification.channel.name, notification.message,
                  dt_to_text(notification.created_at), flag(notification.is_read))
        with self._db.connection() as conn:
            if notification.id is None:
                new_id = conn.execute(
                    "INSERT INTO notifications (recipient_id, incident_id, event_type, channel, "
                    "message, created_at, is_read) VALUES (?, ?, ?, ?, ?, ?, ?)", values).lastrowid
                return replace(notification, id=new_id)
            updated = conn.execute(
                "UPDATE notifications SET recipient_id = ?, incident_id = ?, event_type = ?, "
                "channel = ?, message = ?, created_at = ?, is_read = ? WHERE id = ?",
                (*values, notification.id)).rowcount
            if updated == 0:
                raise PersistenceError(f"Notification {notification.id} does not exist")
        return notification

    def find_by_recipient(self, user_id: int, limit: int) -> list[Notification]:
        """Newest first, at most `limit` rows."""
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM notifications WHERE recipient_id = ? "
                                "ORDER BY created_at DESC, id DESC LIMIT ?",
                                (user_id, max(0, limit))).fetchall()
        return [_notification(r) for r in rows]

    def count_unread(self, user_id: int) -> int:
        with self._db.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM notifications "
                                "WHERE recipient_id = ? AND is_read = 0", (user_id,)).fetchone()[0]

    def mark_read(self, notification_id: int) -> None:
        with self._db.connection() as conn:
            conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))

    def mark_all_read(self, user_id: int) -> None:
        with self._db.connection() as conn:
            conn.execute("UPDATE notifications SET is_read = 1 WHERE recipient_id = ?", (user_id,))
