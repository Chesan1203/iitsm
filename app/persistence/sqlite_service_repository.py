from __future__ import annotations

import sqlite3

from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.it_service import ITService
from app.persistence.codec import flag, level_from_int, level_to_int, placeholders
from app.persistence.database import Database
from app.ports.repositories import ServiceRepository


def service_from_row(row: sqlite3.Row) -> ITService:
    try:
        return ITService(row["name"], row["description"],
                         level_from_int(row["business_criticality"]),
                         row["sla_policy_id"], bool(row["active"]), id=row["id"])
    except InvalidInputError as exc:
        raise PersistenceError(f"Stored service {row['id']} is invalid: {exc}") from exc


def services_by_ids(conn: sqlite3.Connection, ids) -> dict[int, ITService]:
    wanted = sorted({i for i in ids if i is not None})
    if not wanted:
        return {}
    rows = conn.execute(f"SELECT * FROM it_services WHERE id IN ({placeholders(len(wanted))})",
                        wanted).fetchall()
    return {r["id"]: service_from_row(r) for r in rows}


class SqliteServiceRepository(ServiceRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, service: ITService) -> ITService:
        values = (service.name, service.description, level_to_int(service.business_criticality),
                  service.sla_policy_id, flag(service.active))
        with self._db.connection() as conn:
            if service.id is None:
                new_id = conn.execute(
                    "INSERT INTO it_services (name, description, business_criticality, "
                    "sla_policy_id, active) VALUES (?, ?, ?, ?, ?)", values).lastrowid
            else:
                updated = conn.execute(
                    "UPDATE it_services SET name = ?, description = ?, business_criticality = ?, "
                    "sla_policy_id = ?, active = ? WHERE id = ?", (*values, service.id)).rowcount
                if updated == 0:
                    raise PersistenceError(f"Service {service.id} does not exist")
                new_id = None
        if new_id is not None:
            service.assign_id(new_id)
        return service

    def find_by_id(self, id: int) -> ITService | None:
        with self._db.connection() as conn:
            row = conn.execute("SELECT * FROM it_services WHERE id = ?", (id,)).fetchone()
        return None if row is None else service_from_row(row)

    def find_all(self) -> list[ITService]:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM it_services ORDER BY id").fetchall()
        return [service_from_row(r) for r in rows]

    def exists_by_name(self, name: str) -> bool:
        """Case-insensitive, so 'payment' is treated as taken when 'Payment' exists."""
        with self._db.connection() as conn:
            row = conn.execute("SELECT 1 FROM it_services WHERE lower(name) = lower(?)",
                               (name,)).fetchone()
        return row is not None
