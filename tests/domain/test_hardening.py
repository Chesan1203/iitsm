from datetime import datetime, timezone

import pytest

from app.domain.enums import AdminLevel, EscalationLevel, Level, Priority, SlaStatus
from app.domain.exceptions import InvalidInputError
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.user import Employee, User
from app.domain.sla.sla_calculator import SlaCalculator, SlaCheckResult
from app.domain.strategies.priority import PriorityResult
from tests.domain.helpers import (
    T0, at, make_default_policy, make_employee, make_incident, make_incident_in,
)
from app.domain.enums import IncidentStatus as S

AWARE = datetime(2026, 11, 14, 10, 5, tzinfo=timezone.utc)


# ---- time zones are rejected at the door -----------------------------------------

def test_zone_aware_datetimes_are_rejected_where_comparisons_happen():
    inc = make_incident_in(S.ASSIGNED)
    emp, cat, svc = inc.reporter, inc.category, inc.affected_service
    with pytest.raises(InvalidInputError) as e:
        Incident("t", "d", emp, cat, svc, Level.LOW, Level.LOW, 1, AWARE)
    assert e.value.field == "created_at"
    with pytest.raises(InvalidInputError):
        SlaTracker(AWARE, T0)
    with pytest.raises(InvalidInputError):
        SlaTracker(T0, AWARE)
    with pytest.raises(InvalidInputError):
        SlaCalculator().create_tracker(Priority.P1, make_default_policy(), AWARE)
    for call in (lambda: SlaCalculator().evaluate(inc, AWARE),
                 lambda: EscalationPolicy().evaluate(inc, AWARE),
                 lambda: CorrelationDetector().find_groups([inc], AWARE)):
        with pytest.raises(InvalidInputError):
            call()


# ---- ids and the system user -------------------------------------------------------

def test_only_the_system_user_has_id_zero():
    for bad in (0, -1, True, "1"):
        with pytest.raises(InvalidInputError):
            Employee("emp", "Emp", "e@x.com", "hash", id=bad)
    assert User.system().id == 0 and make_employee().id == 1


def test_the_shared_system_user_cannot_be_changed():
    system = User.system()
    for change in (system.deactivate, system.activate):
        with pytest.raises(InvalidInputError):
            change()
    assert system.active and system.is_system


# ---- results validate themselves --------------------------------------------------

def test_priority_result_validates_its_fields():
    for bad in ((0, Priority.P1, "x"), (5, "P1", "x"), (5, Priority.P1, "  "), (2.5, Priority.P1, "x")):
        with pytest.raises(InvalidInputError):
            PriorityResult(*bad)
    assert PriorityResult(27, Priority.P1, "3×3×3 = 27, P1").score == 27


def test_apply_sla_result_rejects_a_bad_status():
    inc = make_incident_in(S.ASSIGNED)
    with pytest.raises(InvalidInputError):
        inc.apply_sla_result(at(1), SlaCheckResult("VIOLATED", []))
    assert inc.sla_tracker.status is SlaStatus.ON_TRACK


def test_a_new_incident_has_no_pending_information_request_and_no_observers_noise():
    assert make_incident().has_pending_info_request is False
