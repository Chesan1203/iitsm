from app.domain.enums import Level
from app.domain.models._entity import Entity
from app.domain.models._validation import optional_text, require_instance, require_int_min, require_text


class ITService(Entity):
    """Immutable. To change a service, build a new one with the same id and save it."""

    def __init__(self, name: str, description: str, business_criticality: Level,
                 sla_policy_id: int | None = None, active: bool = True,
                 *, id: int | None = None):
        super().__init__(id)
        self._name = require_text(name, "name")
        self._description = optional_text(description, "description")
        self._business_criticality = require_instance(business_criticality, Level, "business_criticality")
        self._sla_policy_id = None if sla_policy_id is None else require_int_min(sla_policy_id, 1, "sla_policy_id")
        self._active = bool(active)

    @property
    def name(self) -> str: return self._name
    @property
    def description(self) -> str: return self._description
    @property
    def business_criticality(self) -> Level: return self._business_criticality
    @property
    def sla_policy_id(self) -> int | None: return self._sla_policy_id
    @property
    def active(self) -> bool: return self._active

    def _key(self) -> tuple:
        return (self._id, self._name, self._description, self._business_criticality,
                self._sla_policy_id, self._active)

    def __eq__(self, other) -> bool:
        return isinstance(other, ITService) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(("ITService", self._name))

    def __repr__(self) -> str:
        return f"ITService(id={self._id}, name={self._name!r})"
