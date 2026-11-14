from app.domain.business_rules import BusinessRules as R
from app.domain.enums import EscalationLevel, Priority
from app.domain.exceptions import ITSMError, InvalidInputError, NotFoundError, IncidentNotFoundError


def test_priority_labels():
    assert [p.label for p in Priority] == ["Critical", "High", "Medium", "Low"]


def test_thresholds_strictly_descending():
    assert R.P1_MIN_SCORE > R.P2_MIN_SCORE > R.P3_MIN_SCORE > 1


def test_recommendation_weights_sum_to_100():
    assert R.WEIGHT_SKILL + R.WEIGHT_LOAD + R.WEIGHT_EXPERIENCE + R.WEIGHT_SERVICE_HISTORY == 100


def test_sla_targets_cover_all_priorities_and_response_before_resolution():
    assert set(R.DEFAULT_SLA_TARGET_MINUTES) == set(Priority)
    assert all(resp < res for resp, res in R.DEFAULT_SLA_TARGET_MINUTES.values())


def test_duplicate_weights_sum_to_one():
    assert abs(R.DUPLICATE_TEXT_WEIGHT + R.DUPLICATE_SERVICE_WEIGHT - 1.0) < 1e-9


def test_escalation_levels_ordered():
    assert [e.value for e in EscalationLevel] == [0, 1, 2, 3]


def test_exception_hierarchy_and_fields():
    e = InvalidInputError("bad", field="title")
    assert isinstance(e, ITSMError) and e.field == "title" and e.message == "bad"
    assert issubclass(IncidentNotFoundError, NotFoundError)
