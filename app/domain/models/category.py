from app.domain.models._entity import Entity
from app.domain.models._validation import optional_text, require_text


class Category(Entity):
    """Immutable. To change a category, build a new one with the same id and save it."""

    def __init__(self, name: str, description: str, required_skill: str,
                 active: bool = True, *, id: int | None = None):
        super().__init__(id)
        self._name = require_text(name, "name")
        self._description = optional_text(description, "description")
        self._required_skill = require_text(required_skill, "required_skill")
        self._active = bool(active)

    @property
    def name(self) -> str: return self._name
    @property
    def description(self) -> str: return self._description
    @property
    def required_skill(self) -> str: return self._required_skill
    @property
    def active(self) -> bool: return self._active

    def _key(self) -> tuple:
        return (self._id, self._name, self._description, self._required_skill, self._active)

    def __eq__(self, other) -> bool:
        return isinstance(other, Category) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(("Category", self._name))

    def __repr__(self) -> str:
        return f"Category(id={self._id}, name={self._name!r})"
