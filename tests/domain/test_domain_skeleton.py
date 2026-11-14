from datetime import timedelta

import pytest

from app.domain.enums import IncidentStatus, Level
from app.domain.exceptions import InvalidStateTransitionError
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.intelligence.duplicate_detector import DuplicateDetector
from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.models.user import User
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.state import states
from app.domain.state.incident_state import IncidentState
from app.domain.strategies.assignment import (
    AssignmentStrategy, LoadBasedAssignment, SkillBasedAssignment, WeightedRecommendationStrategy,
)
from app.domain.strategies.priority import (
    PriorityInput, PriorityStrategy, RuleBasedPriorityStrategy, WeightedScorePriorityStrategy,
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


def test_logic_classes_are_stubs_until_their_task():
    inc = make_incident()
    data = PriorityInput(Level.HIGH, Level.HIGH, Level.HIGH, 1)
    with pytest.raises(NotImplementedError):
        WeightedScorePriorityStrategy().calculate(data)
    with pytest.raises(NotImplementedError):
        SkillBasedAssignment().select(inc, [])
    with pytest.raises(NotImplementedError):
        SlaCalculator().evaluate(inc, T0)
    with pytest.raises(NotImplementedError):
        DuplicateDetector().find_similar(inc, [])
    with pytest.raises(NotImplementedError):
        EscalationPolicy().evaluate(inc, T0 + timedelta(minutes=1))
    with pytest.raises(NotImplementedError):
        CorrelationDetector().find_groups([], T0)
