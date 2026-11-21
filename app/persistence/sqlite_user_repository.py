from __future__ import annotations

import sqlite3
from collections import defaultdict

from app.domain.business_rules import BusinessRules
from app.domain.enums import AdminLevel, Role
from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.user import Administrator, Employee, Technician, User
from app.persistence.codec import enum_from_text, enum_to_text, flag, placeholders
from app.persistence.database import Database
from app.ports.repositories import UserRepository


def users_from_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[User]:
    """Builds Employee / Technician / Administrator objects, loading every technician's
    skills with a single query (not one query per technician)."""
    tech_ids = [r["id"] for r in rows if r["role"] == Role.TECHNICIAN.name]
    skills: dict[int, set[str]] = defaultdict(set)
    if tech_ids:
        for s in conn.execute(
                f"SELECT user_id, skill FROM technician_skills "
                f"WHERE user_id IN ({placeholders(len(tech_ids))})", tech_ids):
            skills[s["user_id"]].add(s["skill"])
    return [_user_from_row(r, skills[r["id"]]) for r in rows]


def users_by_ids(conn: sqlite3.Connection, ids) -> dict[int, User]:
    wanted = sorted({i for i in ids if i is not None})
    if not wanted:
        return {}
    rows = conn.execute(f"SELECT * FROM users WHERE id IN ({placeholders(len(wanted))})",
                        wanted).fetchall()
    return {u.id: u for u in users_from_rows(conn, rows)}


def _user_from_row(row: sqlite3.Row, skills: set[str]) -> User:
    role = enum_from_text(Role, row["role"])
    common = dict(id=row["id"], active=bool(row["active"]))
    base = (row["username"], row["full_name"], row["email"], row["password_hash"])
    try:
        if role is Role.EMPLOYEE:
            return Employee(*base, row["department"] or "", **common)
        if role is Role.TECHNICIAN:
            return Technician(
                *base, skills=skills,
                experience_years=0 if row["experience_years"] is None else row["experience_years"],
                available=True if row["available"] is None else bool(row["available"]),
                max_workload=(BusinessRules.MAX_ACTIVE_INCIDENTS if row["max_workload"] is None
                              else row["max_workload"]),
                **common)
        return Administrator(*base, enum_from_text(AdminLevel, row["admin_level"]), **common)
    except InvalidInputError as exc:
        raise PersistenceError(f"Stored user {row['id']} is invalid: {exc}") from exc


def _columns(user: User) -> tuple:
    """Values for the role-specific columns (NULL for roles they do not apply to)."""
    department = admin_level = experience = available = max_workload = None
    if isinstance(user, Employee):
        department = user.department
    elif isinstance(user, Technician):
        experience, available, max_workload = (user.experience_years, flag(user.available),
                                               user.max_workload)
    elif isinstance(user, Administrator):
        admin_level = enum_to_text(user.admin_level)
    return department, admin_level, experience, available, max_workload


class SqliteUserRepository(UserRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, user: User) -> User:
        """Insert when id is None, otherwise update. A technician's skills are replaced in
        the same transaction."""
        if user.is_system:
            raise PersistenceError("The system user is never stored")
        values = (user.username, user.full_name, user.email, user.password_hash,
                  user.role.name, flag(user.active), *_columns(user))
        with self._db.connection() as conn:
            if user.id is None:
                user_id = conn.execute(
                    "INSERT INTO users (username, full_name, email, password_hash, role, active, "
                    "department, admin_level, experience_years, available, max_workload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values).lastrowid
                new_id = user_id
            else:
                user_id = user.id
                updated = conn.execute(
                    "UPDATE users SET username = ?, full_name = ?, email = ?, password_hash = ?, "
                    "role = ?, active = ?, department = ?, admin_level = ?, experience_years = ?, "
                    "available = ?, max_workload = ? WHERE id = ?", (*values, user_id)).rowcount
                if updated == 0:
                    raise PersistenceError(f"User {user_id} does not exist")
                new_id = None
            conn.execute("DELETE FROM technician_skills WHERE user_id = ?", (user_id,))
            if isinstance(user, Technician):
                conn.executemany("INSERT INTO technician_skills (user_id, skill) VALUES (?, ?)",
                                 [(user_id, s) for s in sorted(user.skills)])
        if new_id is not None:
            user.assign_id(new_id)
        return user

    def find_by_id(self, id: int) -> User | None:
        return self._one("SELECT * FROM users WHERE id = ?", (id,))

    def find_by_username(self, username: str) -> User | None:
        return self._one("SELECT * FROM users WHERE username = ?", (username,))

    def find_all(self) -> list[User]:
        return self._many("SELECT * FROM users ORDER BY id", ())

    def find_by_role(self, role: Role) -> list[User]:
        return self._many("SELECT * FROM users WHERE role = ? ORDER BY id", (role.name,))

    def find_admins_by_level(self, level: AdminLevel) -> list[User]:
        """All administrators at that level, including deactivated ones (callers decide)."""
        return self._many("SELECT * FROM users WHERE role = ? AND admin_level = ? ORDER BY id",
                          (Role.ADMINISTRATOR.name, level.name))

    def _one(self, sql: str, params: tuple) -> User | None:
        users = self._many(sql, params)
        return users[0] if users else None

    def _many(self, sql: str, params: tuple) -> list[User]:
        with self._db.connection() as conn:
            return users_from_rows(conn, conn.execute(sql, params).fetchall())
