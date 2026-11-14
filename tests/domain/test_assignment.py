import pytest

from app.domain.exceptions import InvalidInputError
from app.domain.models.candidates import RankedTechnician, TechnicianCandidate
from app.domain.models.user import Technician
from app.domain.strategies.assignment import (
    AssignmentStrategy, LoadBasedAssignment, SkillBasedAssignment, WeightedRecommendationStrategy,
)
from tests.domain.helpers import make_incident

SKILL, LOAD, WEIGHTED = SkillBasedAssignment(), LoadBasedAssignment(), WeightedRecommendationStrategy()
INCIDENT = make_incident()          # category "Database", required skill "Database"


def tech(id, skills, experience, available=True, max_workload=5, active=True):
    return Technician(f"tech{id}", f"Tech {id}", f"t{id}@x.com", "hash", skills, experience,
                      available, max_workload, id=id, active=active)


def cand(technician, active_count, resolved=0):
    return TechnicianCandidate(technician, active_count, resolved)


def ids(ranked):
    return [r.technician.id for r in ranked]


def fleet():
    """Hand-built technicians; ids are in the comments below."""
    return [
        cand(tech(1, {"Database"}, 2), 3, 0),                       # skilled, busy
        cand(tech(2, {"Database", "Network"}, 8), 1, 3),            # skilled, experienced
        cand(tech(3, {"Network"}, 10), 0, 0),                       # idle but wrong skill
        cand(tech(4, {"Database"}, 5), 1, 5),                       # same load as 2, knows the service
        cand(tech(5, {"Database"}, 9, available=False), 0, 0),      # unavailable
        cand(tech(6, {"Database"}, 9), 5, 0),                       # at max workload
        cand(tech(7, {"Database"}, 9, active=False), 0, 0),         # inactive account
    ]


def test_skill_based_picks_the_least_loaded_skilled_technician():
    ranked = SKILL.rank(INCIDENT, fleet())
    assert ids(ranked) == [2, 4, 1]                                 # tie on load: more experience first
    assert SKILL.select(INCIDENT, fleet()).id == 2
    assert ranked[0].reasons[0] == "has skill Database"


def test_load_based_ignores_skills():
    assert ids(LOAD.rank(INCIDENT, fleet())) == [3, 2, 4, 1]
    assert LOAD.select(INCIDENT, fleet()).id == 3


def test_weighted_recommendation_scores_exactly_as_specified():
    ranked = WEIGHTED.rank(INCIDENT, fleet())
    assert [(r.technician.id, r.score) for r in ranked] == [(4, 86.5), (2, 85.0), (1, 55.0), (3, 45.0)]
    # tech 4: 40 (skill) + 30x0.8 (load) + 15x0.5 (5 of 10 years) + 15x1 (5 resolved here)
    assert WEIGHTED.select(INCIDENT, fleet()).id == 4


def test_weighted_reasons_are_readable():
    best, unskilled = WEIGHTED.rank(INCIDENT, fleet())[0], WEIGHTED.rank(INCIDENT, fleet())[-1]
    assert best.reasons == ["has skill Database", "1 of 5 slots used", "5 years experience",
                            "resolved 5 incidents on this service"]
    assert unskilled.reasons[0] == "lacks skill Database"


def test_strategies_are_swappable_and_pick_differently():
    picks = {}
    for strategy in (SKILL, LOAD, WEIGHTED):
        assert isinstance(strategy, AssignmentStrategy)
        picks[strategy.name] = strategy.select(INCIDENT, fleet()).id
    assert picks == {"skill_based": 2, "load_based": 3, "weighted_recommendation": 4}


def test_nobody_qualifies_returns_none_and_an_empty_ranking():
    nobody = [fleet()[4], fleet()[5], fleet()[6]]                   # unavailable, full, inactive
    for strategy in (SKILL, LOAD, WEIGHTED):
        assert strategy.select(INCIDENT, nobody) is None
        assert strategy.rank(INCIDENT, nobody) == []
        assert strategy.select(INCIDENT, []) is None


def test_skill_based_returns_none_when_only_unskilled_technicians_are_free():
    only_network = [fleet()[2]]
    assert SKILL.select(INCIDENT, only_network) is None
    assert LOAD.select(INCIDENT, only_network).id == 3
    assert WEIGHTED.select(INCIDENT, only_network).id == 3          # recommended, just without the skill points


def test_ties_are_broken_by_experience_then_lowest_id_whatever_the_input_order():
    twins = [cand(tech(9, {"Database"}, 5), 2), cand(tech(8, {"Database"}, 5), 2)]
    for strategy in (SKILL, LOAD, WEIGHTED):
        assert strategy.select(INCIDENT, twins).id == 8
        assert strategy.select(INCIDENT, list(reversed(twins))).id == 8
    veteran = twins + [cand(tech(10, {"Database"}, 9), 2)]
    assert SKILL.select(INCIDENT, veteran).id == 10


def test_each_technician_has_their_own_workload_limit():
    small = tech(11, {"Database"}, 3, max_workload=2)
    assert LOAD.select(INCIDENT, [cand(small, 2)]) is None
    ranked = SKILL.rank(INCIDENT, [cand(small, 1)])
    assert ids(ranked) == [11] and ranked[0].score == 50.0          # 1 of 2 slots used


def test_skill_matching_ignores_case():
    assert SKILL.select(INCIDENT, [cand(tech(12, {"database"}, 1), 0)]).id == 12


def test_invalid_candidates_are_rejected():
    for strategy in (SKILL, LOAD, WEIGHTED):
        with pytest.raises(InvalidInputError):
            strategy.rank(INCIDENT, ["tech1"])
    with pytest.raises(InvalidInputError):
        TechnicianCandidate("tech1", 0, 0)
    with pytest.raises(InvalidInputError):
        cand(tech(13, {"Database"}, 1), -1)
    with pytest.raises(InvalidInputError):
        cand(tech(13, {"Database"}, 1), 0, -1)


def test_rank_returns_ranked_technician_objects():
    ranked = WEIGHTED.rank(INCIDENT, fleet())
    assert all(isinstance(r, RankedTechnician) for r in ranked)
