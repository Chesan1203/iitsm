from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.enums import Level, Priority

_NOT_YET = "Implemented in task T5"


@dataclass(frozen=True)
class PriorityInput:
    impact: Level
    urgency: Level
    criticality: Level
    affected_users: int


@dataclass(frozen=True)
class PriorityResult:
    score: int
    priority: Priority
    explanation: str


class PriorityStrategy(ABC):
    @abstractmethod
    def calculate(self, data: PriorityInput) -> PriorityResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class WeightedScorePriorityStrategy(PriorityStrategy):
    @property
    def name(self) -> str:
        return "weighted_score"

    def calculate(self, data: PriorityInput) -> PriorityResult:
        raise NotImplementedError(_NOT_YET)


class RuleBasedPriorityStrategy(PriorityStrategy):
    @property
    def name(self) -> str:
        return "rule_based"

    def calculate(self, data: PriorityInput) -> PriorityResult:
        raise NotImplementedError(_NOT_YET)
