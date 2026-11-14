from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain.models.candidates import RankedTechnician, TechnicianCandidate
from app.domain.models.user import Technician

if TYPE_CHECKING:
    from app.domain.models.incident import Incident

_NOT_YET = "Implemented in task T7"


class AssignmentStrategy(ABC):
    @abstractmethod
    def select(self, incident: Incident, candidates: list[TechnicianCandidate]) -> Technician | None:
        """The chosen technician, or None when nobody qualifies."""

    @abstractmethod
    def rank(self, incident: Incident, candidates: list[TechnicianCandidate]) -> list[RankedTechnician]:
        """Every qualifying candidate, best first, with a score and readable reasons."""

    @property
    @abstractmethod
    def name(self) -> str: ...


class SkillBasedAssignment(AssignmentStrategy):
    @property
    def name(self) -> str:
        return "skill_based"

    def select(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)

    def rank(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)


class LoadBasedAssignment(AssignmentStrategy):
    @property
    def name(self) -> str:
        return "load_based"

    def select(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)

    def rank(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)


class WeightedRecommendationStrategy(AssignmentStrategy):
    """The 'smart technician recommendation' feature."""

    @property
    def name(self) -> str:
        return "weighted_recommendation"

    def select(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)

    def rank(self, incident, candidates):
        raise NotImplementedError(_NOT_YET)
