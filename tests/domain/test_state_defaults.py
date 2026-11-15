"""Every action that the lifecycle table does not allow in a state must fail with
InvalidStateTransitionError, whoever asks. Exercises each default method of IncidentState
through the public Incident API."""
import pytest

from app.domain.enums import (
    AdminLevel, EscalationLevel as L, IncidentStatus as S, NoteType, Priority, SlaStatus,
)
from app.domain.exceptions import InvalidStateTransitionError
from app.domain.intelligence.escalation_policy import EscalationDecision
from app.domain.models.user import User
from app.domain.sla.sla_calculator import SlaCheckResult
from app.domain.state.state_factory import IncidentStateFactory
from tests.domain.helpers import (
    at, make_admin, make_incident_in, make_priority_result, make_technician, make_tracker,
)
from tests.domain.test_state_machine import ACTIONS, LEGAL

SYSTEM = User.system()


def calls(inc):
    admin, tech, emp = make_admin(), make_technician(), inc.reporter
    other = make_technician(id=3, username="tech2")
    decision = EscalationDecision(L.IT_MANAGER, AdminLevel.IT_MANAGER, "x")
    t = at(50)
    return {
        "record_creation": lambda: inc.record_creation(emp, t),
        "classify": lambda: inc.classify(SYSTEM, t, make_priority_result(), make_tracker()),
        "assign_to": lambda: inc.assign_to(admin, t, tech, 0),
        "reassign": lambda: inc.reassign(admin, t, other, 0),
        "acknowledge": lambda: inc.acknowledge(tech, t),
        "start_investigation": lambda: inc.start_investigation(tech, t),
        "add_note": lambda: inc.add_note(tech, t, "n", NoteType.INVESTIGATION),
        "request_info": lambda: inc.request_info(tech, t, "q"),
        "respond_to_info": lambda: inc.respond_to_info(emp, t, "a"),
        "resolve": lambda: inc.resolve(tech, t, "s", "d"),
        "verify": lambda: inc.verify(emp, t),
        "reject_resolution": lambda: inc.reject_resolution(emp, t, "r"),
        "close": lambda: inc.close(emp, t),
        "submit_feedback": lambda: inc.submit_feedback(emp, t, 5, "c"),
        "escalate": lambda: inc.escalate(admin, t, decision),
        "change_priority": lambda: inc.change_priority(admin, t, Priority.P2, "r", make_tracker()),
        "mark_possible_duplicate": lambda: inc.mark_possible_duplicate(admin, t, "INC-1", 0.5),
        "apply_sla_result": lambda: inc.apply_sla_result(t, SlaCheckResult(SlaStatus.ON_TRACK, [])),
    }


def test_every_action_not_in_the_lifecycle_table_is_rejected_in_every_state():
    checked = 0
    for status in S:
        legal = LEGAL[type(IncidentStateFactory.for_status(status))]
        inc = make_incident_in(status)
        before = inc.snapshot()
        table = calls(inc)
        assert set(table) == set(ACTIONS)
        for action in ACTIONS:
            if action in legal:
                continue
            with pytest.raises(InvalidStateTransitionError) as e:
                table[action]()
            assert f"incident that is {status.name}" in str(e.value), (status, action)
            checked += 1
        assert inc.snapshot() == before, status                     # nothing was changed
    assert checked == 8 * 18 - sum(len(v) for v in LEGAL.values())   # the whole matrix was covered
