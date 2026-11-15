from app.domain.exceptions import InvalidInputError
from app.domain.models._validation import require_int_min


class Entity:
    """Base for objects that get a database id. The id is write-once."""

    def __init__(self, id: int | None = None):
        self._id = None if id is None else require_int_min(id, 1, "id")

    @property
    def id(self) -> int | None:
        return self._id

    def assign_id(self, new_id: int) -> None:
        """Called by a repository on first save. Cannot be called twice."""
        if self._id is not None:
            raise InvalidInputError("Identity is already assigned", "id")
        self._id = require_int_min(new_id, 1, "id")
