from dataclasses import dataclass

from app.domain.models._validation import require_instance, require_int_min
from app.domain.models.user import Technician


@dataclass(frozen=True)
class TechnicianCandidate:
    technician: Technician
    active_incident_count: int
    resolved_on_this_service_count: int

    def __post_init__(self):
        require_instance(self.technician, Technician, "technician")
        require_int_min(self.active_incident_count, 0, "active_incident_count")
        require_int_min(self.resolved_on_this_service_count, 0, "resolved_on_this_service_count")


@dataclass(frozen=True)
class RankedTechnician:
    technician: Technician
    score: float
    reasons: list[str]
