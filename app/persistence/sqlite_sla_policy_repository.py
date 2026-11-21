from __future__ import annotations

import sqlite3
from collections import defaultdict

from app.domain.enums import Priority
from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.persistence.codec import enum_from_text, flag, placeholders
from app.persistence.database import Database
from app.ports.repositories import SlaPolicyRepository


class SqliteSlaPolicyRepository(SlaPolicyRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, policy: SlaPolicy) -> SlaPolicy:
        """Writes the policy row and replaces its target rows in one transaction."""
        with self._db.connection() as conn:
            if policy.id is None:
                policy_id = conn.execute("INSERT INTO sla_policies (name, is_default) VALUES (?, ?)",
                                         (policy.name, flag(policy.is_default))).lastrowid
                new_id = policy_id
            else:
                policy_id = policy.id
                updated = conn.execute("UPDATE sla_policies SET name = ?, is_default = ? WHERE id = ?",
                                       (policy.name, flag(policy.is_default), policy_id)).rowcount
                if updated == 0:
                    raise PersistenceError(f"SLA policy {policy_id} does not exist")
                new_id = None
            conn.execute("DELETE FROM sla_targets WHERE policy_id = ?", (policy_id,))
            conn.executemany(
                "INSERT INTO sla_targets (policy_id, priority, response_minutes, resolution_minutes) "
                "VALUES (?, ?, ?, ?)",
                [(policy_id, priority.name, t.response_minutes, t.resolution_minutes)
                 for priority, t in policy.targets.items()])
        if new_id is not None:
            policy.assign_id(new_id)
        return policy

    def find_by_id(self, id: int) -> SlaPolicy | None:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM sla_policies WHERE id = ?", (id,)).fetchall()
            return self._build(conn, rows)[0] if rows else None

    def find_default(self) -> SlaPolicy | None:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM sla_policies WHERE is_default = 1 "
                                "ORDER BY id LIMIT 1").fetchall()
            return self._build(conn, rows)[0] if rows else None

    def find_all(self) -> list[SlaPolicy]:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM sla_policies ORDER BY id").fetchall()
            return self._build(conn, rows)

    @staticmethod
    def _build(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[SlaPolicy]:
        """Builds policies from rows, loading all their targets with one query."""
        ids = [r["id"] for r in rows]
        targets: dict[int, dict[Priority, SlaTarget]] = defaultdict(dict)
        if ids:
            for t in conn.execute(
                    f"SELECT * FROM sla_targets WHERE policy_id IN ({placeholders(len(ids))})", ids):
                targets[t["policy_id"]][enum_from_text(Priority, t["priority"])] = SlaTarget(
                    t["response_minutes"], t["resolution_minutes"])
        try:
            return [SlaPolicy(r["name"], bool(r["is_default"]), targets[r["id"]], id=r["id"])
                    for r in rows]
        except InvalidInputError as exc:
            raise PersistenceError(f"Stored SLA policy is invalid: {exc}") from exc
