from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.business_rules import BusinessRules
from app.domain.enums import Level, Priority
from app.domain.models._validation import require_instance, require_int_min


@dataclass(frozen=True)
class PriorityInput:
    impact: Level
    urgency: Level
    criticality: Level
    affected_users: int

    def __post_init__(self):
        require_instance(self.impact, Level, "impact")
        require_instance(self.urgency, Level, "urgency")
        require_instance(self.criticality, Level, "criticality")
        require_int_min(self.affected_users, 1, "affected_users")


@dataclass(frozen=True)
class PriorityResult:
    score: int
    priority: Priority
    explanation: str


def score_to_priority(score: int) -> Priority:
    """Map a raw score (1 to 27) to a priority using the BusinessRules thresholds."""
    if score >= BusinessRules.P1_MIN_SCORE:
        return Priority.P1
    if score >= BusinessRules.P2_MIN_SCORE:
        return Priority.P2
    if score >= BusinessRules.P3_MIN_SCORE:
        return Priority.P3
    return Priority.P4


def raise_one_level(priority: Priority) -> Priority:
    """P4 -> P3 -> P2 -> P1. P1 stays P1."""
    return Priority(max(Priority.P1.value, priority.value - 1))


class PriorityStrategy(ABC):
    @abstractmethod
    def calculate(self, data: PriorityInput) -> PriorityResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class WeightedScorePriorityStrategy(PriorityStrategy):
    """score = impact x urgency x business criticality (each 1 to 3, so 1 to 27).

    The thresholds and the bump live in BusinessRules. Having many affected users raises
    the priority by one level (P1 stays P1); the raw score is left as calculated.
    """

    @property
    def name(self) -> str:
        return "weighted_score"

    def calculate(self, data: PriorityInput) -> PriorityResult:
        require_instance(data, PriorityInput, "data")
        i, u, c = data.impact.value, data.urgency.value, data.criticality.value
        score = i * u * c
        base = score_to_priority(score)
        priority = base
        text = f"{i}×{u}×{c} = {score}, {base.name}"
        if data.affected_users >= BusinessRules.AFFECTED_USERS_BUMP_THRESHOLD:
            priority = raise_one_level(base)
            users = f"{data.affected_users} affected users (≥{BusinessRules.AFFECTED_USERS_BUMP_THRESHOLD})"
            if priority is base:
                text += f"; {users} cannot raise it above {base.name}"
            else:
                text += f"; {users} raise it to {priority.name}"
        return PriorityResult(score, priority, text)


class RuleBasedPriorityStrategy(PriorityStrategy):
    """A visibly different strategy: one override rule, then the weighted score.

    Rule: HIGH business criticality and HIGH impact is always P1, whatever the urgency.
    Otherwise it falls back to WeightedScorePriorityStrategy (composition), including the
    affected-users bump.
    """

    def __init__(self):
        self._fallback = WeightedScorePriorityStrategy()

    @property
    def name(self) -> str:
        return "rule_based"

    def calculate(self, data: PriorityInput) -> PriorityResult:
        require_instance(data, PriorityInput, "data")
        weighted = self._fallback.calculate(data)
        if data.criticality is Level.HIGH and data.impact is Level.HIGH:
            return PriorityResult(
                weighted.score, Priority.P1,
                f"Rule: HIGH business criticality and HIGH impact is always P1 (score {weighted.score})")
        return PriorityResult(weighted.score, weighted.priority,
                              f"No override rule matched; {weighted.explanation}")
