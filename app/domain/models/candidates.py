from dataclasses import dataclass

from app.domain.models.user import Technician


@dataclass(frozen=True)
class TechnicianCandidate:
    technician: Technician
    active_incident_count: int
    resolved_on_this_service_count: int


@dataclass(frozen=True)
class RankedTechnician:
    technician: Technician
    score: float
    reasons: list[str]
