from __future__ import annotations

import sqlite3

from app.domain.exceptions import InvalidInputError, PersistenceError
from app.domain.models.category import Category
from app.persistence.codec import flag, placeholders
from app.persistence.database import Database
from app.ports.repositories import CategoryRepository


def category_from_row(row: sqlite3.Row) -> Category:
    try:
        return Category(row["name"], row["description"], row["required_skill"],
                        bool(row["active"]), id=row["id"])
    except InvalidInputError as exc:
        raise PersistenceError(f"Stored category {row['id']} is invalid: {exc}") from exc


def categories_by_ids(conn: sqlite3.Connection, ids) -> dict[int, Category]:
    wanted = sorted({i for i in ids if i is not None})
    if not wanted:
        return {}
    rows = conn.execute(f"SELECT * FROM categories WHERE id IN ({placeholders(len(wanted))})",
                        wanted).fetchall()
    return {r["id"]: category_from_row(r) for r in rows}


class SqliteCategoryRepository(CategoryRepository):
    def __init__(self, db: Database):
        self._db = db

    def save(self, category: Category) -> Category:
        values = (category.name, category.description, category.required_skill,
                  flag(category.active))
        with self._db.connection() as conn:
            if category.id is None:
                new_id = conn.execute(
                    "INSERT INTO categories (name, description, required_skill, active) "
                    "VALUES (?, ?, ?, ?)", values).lastrowid
            else:
                updated = conn.execute(
                    "UPDATE categories SET name = ?, description = ?, required_skill = ?, "
                    "active = ? WHERE id = ?", (*values, category.id)).rowcount
                if updated == 0:
                    raise PersistenceError(f"Category {category.id} does not exist")
                new_id = None
        if new_id is not None:
            category.assign_id(new_id)        # after commit, so a rollback never leaves an id behind
        return category

    def find_by_id(self, id: int) -> Category | None:
        with self._db.connection() as conn:
            row = conn.execute("SELECT * FROM categories WHERE id = ?", (id,)).fetchone()
        return None if row is None else category_from_row(row)

    def find_all(self) -> list[Category]:
        with self._db.connection() as conn:
            rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        return [category_from_row(r) for r in rows]
