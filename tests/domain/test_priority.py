from itertools import product

import pytest

from app.domain.enums import Level, Priority
from app.domain.exceptions import InvalidInputError
from app.domain.strategies.priority import (
    PriorityInput, PriorityStrategy, RuleBasedPriorityStrategy, WeightedScorePriorityStrategy,
    raise_one_level, score_to_priority,
)

L, M, H = Level.LOW, Level.MEDIUM, Level.HIGH
WEIGHTED = WeightedScorePriorityStrategy()
RULES = RuleBasedPriorityStrategy()


def calc(strategy, impact, urgency, criticality, users=1):
    return strategy.calculate(PriorityInput(impact, urgency, criticality, users))


# ---- thresholds -------------------------------------------------------------------

def test_score_thresholds_at_every_boundary():
    expected = {1: Priority.P4, 3: Priority.P4, 4: Priority.P3, 8: Priority.P3,
                9: Priority.P2, 17: Priority.P2, 18: Priority.P1, 27: Priority.P1}
    for score, priority in expected.items():
        assert score_to_priority(score) is priority, score


def test_reachable_scores_and_their_distribution():
    """Only products of three numbers from 1..3 occur. 27 combinations, 10 distinct scores."""
    scores, counts = set(), {p: 0 for p in Priority}
    for i, u, c in product((L, M, H), repeat=3):
        result = calc(WEIGHTED, i, u, c)
        scores.add(result.score)
        counts[result.priority] += 1
    assert scores == {1, 2, 3, 4, 6, 8, 9, 12, 18, 27}
    assert counts == {Priority.P1: 4, Priority.P2: 6, Priority.P3: 10, Priority.P4: 7}


def test_raise_one_level_and_p1_ceiling():
    assert [raise_one_level(p) for p in (Priority.P4, Priority.P3, Priority.P2, Priority.P1)] == [
        Priority.P3, Priority.P2, Priority.P1, Priority.P1]


# ---- weighted score ---------------------------------------------------------------

def test_weighted_score_values_and_explanations():
    result = calc(WEIGHTED, H, H, M)
    assert (result.score, result.priority, result.explanation) == (18, Priority.P1, "3×3×2 = 18, P1")
    result = calc(WEIGHTED, H, H, H)
    assert (result.score, result.priority, result.explanation) == (27, Priority.P1, "3×3×3 = 27, P1")
    assert calc(WEIGHTED, M, M, M).priority is Priority.P3          # 8
    assert calc(WEIGHTED, H, M, M).priority is Priority.P2          # 12
    assert calc(WEIGHTED, L, L, L).priority is Priority.P4          # 1


def test_business_criticality_matters():
    """Same impact and urgency: a payment outage outranks a printer fault."""
    assert calc(WEIGHTED, H, H, H).priority is Priority.P1
    assert calc(WEIGHTED, H, H, L).priority is Priority.P2          # 9


def test_affected_users_bump_at_the_boundary():
    assert calc(WEIGHTED, M, M, M, 49).priority is Priority.P3      # no bump
    bumped = calc(WEIGHTED, M, M, M, 50)
    assert bumped.priority is Priority.P2 and bumped.score == 8     # one level up, score unchanged
    assert "50 affected users" in bumped.explanation and "P2" in bumped.explanation


def test_bump_raises_exactly_one_level_and_p1_stays_p1():
    assert calc(WEIGHTED, L, L, L, 5000).priority is Priority.P3    # P4 -> P3, not further
    top = calc(WEIGHTED, H, H, H, 5000)
    assert top.priority is Priority.P1 and "cannot raise it above P1" in top.explanation


def test_input_is_validated():
    for bad in ((2, M, M, 1), (M, "HIGH", M, 1), (M, M, None, 1), (M, M, M, 0), (M, M, M, True)):
        with pytest.raises(InvalidInputError):
            PriorityInput(*bad)
    with pytest.raises(InvalidInputError):
        WEIGHTED.calculate((3, 3, 3, 1))


# ---- rule based -------------------------------------------------------------------

def test_rule_overrides_the_score_for_high_criticality_and_high_impact():
    weighted, ruled = calc(WEIGHTED, H, L, H), calc(RULES, H, L, H)   # score 9
    assert weighted.priority is Priority.P2
    assert ruled.priority is Priority.P1 and ruled.score == 9
    assert ruled.explanation.startswith("Rule: HIGH business criticality and HIGH impact is always P1")


def test_rule_based_falls_back_to_the_weighted_score_everywhere_else():
    for i, u, c in product((L, M, H), repeat=3):
        if i is H and c is H:
            continue
        for users in (1, 50):
            assert calc(RULES, i, u, c, users).priority is calc(WEIGHTED, i, u, c, users).priority
    fallback = calc(RULES, M, M, M, 50)
    assert fallback.priority is Priority.P2 and fallback.explanation.startswith("No override rule matched")


def test_strategies_are_interchangeable_behind_one_interface():
    data = PriorityInput(H, L, H, 1)
    outcomes = {}
    for strategy in (WEIGHTED, RULES):
        assert isinstance(strategy, PriorityStrategy)
        outcomes[strategy.name] = strategy.calculate(data).priority
    assert outcomes == {"weighted_score": Priority.P2, "rule_based": Priority.P1}
