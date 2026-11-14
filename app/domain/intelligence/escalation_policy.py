from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import AdminLevel, EscalationLevel

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_NOT_YET = "Implemented in task T8"


@dataclass(frozen=True)
class EscalationDecision:
    new_level: EscalationLevel
    target_admin_level: AdminLevel
    reason: str


class EscalationPolicy:
    """Stateless."""

    def evaluate(self, incident: Incident, now: datetime) -> EscalationDecision | None:
        raise NotImplementedError(_NOT_YET)
