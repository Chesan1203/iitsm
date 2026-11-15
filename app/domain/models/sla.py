from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import Priority, SlaEventType
from app.domain.exceptions import MissingSlaConfigurationError
from app.domain.models._entity import Entity
from app.domain.models._validation import require_instance, require_int_min, require_text


@dataclass(frozen=True)
class SlaTarget:
    response_minutes: int
    resolution_minutes: int

    def __post_init__(self):
        require_int_min(self.response_minutes, 1, "response_minutes")
        require_int_min(self.resolution_minutes, 1, "resolution_minutes")


class SlaPolicy(Entity):
    def __init__(self, name: str, is_default: bool = False, targets: dict | None = None,
                 *, id: int | None = None):
        super().__init__(id)
        self._name = require_text(name, "name")
        self._is_default = bool(is_default)
        checked = {}
        for priority, target in (targets or {}).items():
            require_instance(priority, Priority, "targets")
            checked[priority] = require_instance(target, SlaTarget, "targets")
        self._targets = checked

    @property
    def name(self) -> str: return self._name
    @property
    def is_default(self) -> bool: return self._is_default
    @property
    def targets(self) -> dict[Priority, SlaTarget]: return dict(self._targets)

    def target_for(self, priority: Priority) -> SlaTarget:
        try:
            return self._targets[priority]
        except KeyError:
            raise MissingSlaConfigurationError(
                f"SLA policy '{self._name}' has no target for {priority.name}") from None

    def _key(self) -> tuple:
        return (self._id, self._name, self._is_default, tuple(sorted(self._targets.items(), key=lambda kv: kv[0].value)))

    def __eq__(self, other) -> bool:
        return isinstance(other, SlaPolicy) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(("SlaPolicy", self._name))

    def __repr__(self) -> str:
        return f"SlaPolicy(id={self._id}, name={self._name!r})"


@dataclass(frozen=True, kw_only=True)
class SlaEvent:
    id: int | None = None
    incident_id: int
    event_type: SlaEventType
    recorded_at: datetime

    def __post_init__(self):
        require_instance(self.event_type, SlaEventType, "event_type")
        require_instance(self.recorded_at, datetime, "recorded_at")
