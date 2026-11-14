import pytest

from app.domain.enums import IncidentStatus
from app.domain.exceptions import InvalidStateTransitionError
from app.domain.models.user import User
from app.domain.state import states
from app.domain.state.incident_state import IncidentState
from app.domain.strategies.assignment import (
    AssignmentStrategy, LoadBasedAssignment, SkillBasedAssignment, WeightedRecommendationStrategy,
)
from app.domain.strategies.priority import (
    PriorityStrategy, RuleBasedPriorityStrategy, WeightedScorePriorityStrategy,
)
from tests.domain.helpers import T0, make_incident

ALL_STATES = [states.NewState, states.ClassifiedState, states.AssignedState,
              states.AcknowledgedState, states.InProgressState, states.ResolvedState,
              states.VerifiedState, states.ClosedState]


def test_there_is_one_state_class_per_status_in_lifecycle_order():
    assert [cls().status for cls in ALL_STATES] == list(IncidentStatus)


def test_state_base_class_is_abstract():
    with pytest.raises(TypeError):
        IncidentState()


def test_every_action_is_illegal_by_default_with_a_clear_message():
    state, actor, inc = states.NewState(), User.system(), make_incident()
    with pytest.raises(InvalidStateTransitionError) as e:
        state.close(inc, actor, T0)
    assert str(e.value) == "Cannot close an incident that is NEW"
    with pytest.raises(InvalidStateTransitionError) as e:
        states.ClosedState().start_investigation(inc, actor, T0)
    assert str(e.value) == "Cannot start investigating an incident that is CLOSED"


def test_strategy_interfaces_are_abstract_and_names_are_stable():
    for abstract in (PriorityStrategy, AssignmentStrategy):
        with pytest.raises(TypeError):
            abstract()
    assert WeightedScorePriorityStrategy().name == "weighted_score"
    assert RuleBasedPriorityStrategy().name == "rule_based"
    assert [s().name for s in (SkillBasedAssignment, LoadBasedAssignment,
                               WeightedRecommendationStrategy)] == [
        "skill_based", "load_based", "weighted_recommendation"]
