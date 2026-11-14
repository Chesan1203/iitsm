"""Technician assignment strategies (Strategy pattern).

All three share the same eligibility filter: the technician is active and available and has
fewer active incidents than their own max_workload. They differ in how they pick among the
eligible ones. `select` is the same for all (the first of `rank`), so each strategy only
defines `rank` and `name` (Template Method).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain.business_rules import BusinessRules as R
from app.domain.models._validation import require_instance
from app.domain.models.candidates import RankedTechnician, TechnicianCandidate
from app.domain.models.user import Technician

if TYPE_CHECKING:
    from app.domain.models.incident import Incident


def _eligible(candidates) -> list[TechnicianCandidate]:
    pool = []
    for candidate in candidates:
        require_instance(candidate, TechnicianCandidate, "candidates")
        tech = candidate.technician
        if tech.active and tech.available and candidate.active_incident_count < tech.max_workload:
            pool.append(candidate)
    return pool


def _has_skill(technician: Technician, skill: str) -> bool:
    return skill.casefold() in {s.casefold() for s in technician.skills}


def _tie_key(candidate: TechnicianCandidate) -> tuple:
    """Fewest active incidents, then most experience, then lowest id (so results are predictable)."""
    tech = candidate.technician
    return (candidate.active_incident_count, -tech.experience_years, tech.id or 0)


def _load_score(candidate: TechnicianCandidate) -> float:
    """100 when idle, 0 when at the workload limit."""
    return round(100 * (1 - candidate.active_incident_count / candidate.technician.max_workload), 2)


def _slots(candidate: TechnicianCandidate) -> str:
    return f"{candidate.active_incident_count} of {candidate.technician.max_workload} slots used"


def _years(technician: Technician) -> str:
    return f"{technician.experience_years} years experience"


class AssignmentStrategy(ABC):
    @abstractmethod
    def rank(self, incident: Incident, candidates: list[TechnicianCandidate]) -> list[RankedTechnician]:
        """Every qualifying candidate, best first, with a score and readable reasons."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    def select(self, incident: Incident, candidates: list[TechnicianCandidate]) -> Technician | None:
        """The best qualifying technician, or None when nobody qualifies."""
        ranked = self.rank(incident, candidates)
        return ranked[0].technician if ranked else None


class SkillBasedAssignment(AssignmentStrategy):
    """Only technicians with the category's required skill; fewest active incidents wins.

    The order of `rank` is authoritative (fewest active incidents, then most experience, then
    lowest id). The score shown is the load component (100 = idle).
    """

    @property
    def name(self) -> str:
        return "skill_based"

    def rank(self, incident, candidates):
        skill = incident.category.required_skill
        pool = [c for c in _eligible(candidates) if _has_skill(c.technician, skill)]
        return [RankedTechnician(c.technician, _load_score(c),
                                 [f"has skill {skill}", _slots(c), _years(c.technician)])
                for c in sorted(pool, key=_tie_key)]


class LoadBasedAssignment(AssignmentStrategy):
    """Ignores skills: the technician with the fewest active incidents wins."""

    @property
    def name(self) -> str:
        return "load_based"

    def rank(self, incident, candidates):
        return [RankedTechnician(c.technician, _load_score(c), [_slots(c), _years(c.technician)])
                for c in sorted(_eligible(candidates), key=_tie_key)]


class WeightedRecommendationStrategy(AssignmentStrategy):
    """The 'smart technician recommendation' feature. Score out of 100:

        40 x skill match (1 or 0)
      + 30 x (1 - active / max workload)
      + 15 x (experience years, capped at 10, / 10)
      + 15 x (incidents resolved on this service, capped at 5, / 5)

    Candidates without the skill are still ranked (they just lose the 40 points).
    Ties: higher score, then fewer active incidents, then more experience, then lowest id.
    """

    @property
    def name(self) -> str:
        return "weighted_recommendation"

    def rank(self, incident, candidates):
        skill = incident.category.required_skill
        scored = []
        for c in _eligible(candidates):
            tech = c.technician
            has_skill = _has_skill(tech, skill)
            score = round(
                R.WEIGHT_SKILL * (1 if has_skill else 0)
                + R.WEIGHT_LOAD * (1 - c.active_incident_count / tech.max_workload)
                + R.WEIGHT_EXPERIENCE * min(tech.experience_years, R.EXPERIENCE_CAP_YEARS) / R.EXPERIENCE_CAP_YEARS
                + R.WEIGHT_SERVICE_HISTORY * min(c.resolved_on_this_service_count, R.SERVICE_HISTORY_CAP) / R.SERVICE_HISTORY_CAP,
                2)
            reasons = [f"has skill {skill}" if has_skill else f"lacks skill {skill}", _slots(c),
                       _years(tech), f"resolved {c.resolved_on_this_service_count} incidents on this service"]
            scored.append((score, c, RankedTechnician(tech, score, reasons)))
        scored.sort(key=lambda item: (-item[0], *_tie_key(item[1])))
        return [ranked for _, _, ranked in scored]
