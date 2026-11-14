import dataclasses
from datetime import timedelta

from app.domain.enums import AdminLevel, EscalationLevel as L, IncidentStatus as S, Priority
from app.domain.intelligence.escalation_policy import EscalationDecision, EscalationPolicy
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.domain.observer import IncidentObserver
from tests.domain.helpers import at, make_admin, make_incident, make_incident_in, make_tracker

POLICY = EscalationPolicy()
SYSTEM = User.system()
SEC = timedelta(seconds=1)
DEADLINE = at(5)                       # P1 response deadline of the helper incidents


def level(inc, now):
    decision = POLICY.evaluate(inc, now)
    return decision.new_level if decision else None


def test_the_escalation_timeline():
    inc = make_incident_in(S.ASSIGNED)
    assert level(inc, at(0)) is None
    assert level(inc, DEADLINE) is None                                  # exactly at the deadline
    first = POLICY.evaluate(inc, DEADLINE + SEC)
    assert first.new_level is L.TEAM_LEAD and first.target_admin_level is AdminLevel.TEAM_LEAD
    assert "TEAM_LEAD" in first.reason and "just past" in first.reason
    inc.escalate(SYSTEM, DEADLINE + SEC, first)

    assert level(inc, at(15) - SEC) is None                              # ten minutes not yet over
    second = POLICY.evaluate(inc, at(15))
    assert second.new_level is L.SYSTEM_ADMIN and second.target_admin_level is AdminLevel.SYSTEM_ADMIN
    assert "10 min after" in second.reason
    inc.escalate(SYSTEM, at(15), second)

    assert level(inc, at(25) - SEC) is None
    third = POLICY.evaluate(inc, at(25))
    assert third.new_level is L.IT_MANAGER and third.target_admin_level is AdminLevel.IT_MANAGER
    inc.escalate(SYSTEM, at(25), third)

    assert level(inc, at(35)) is None                                    # nothing above IT_MANAGER
    assert level(inc, at(500)) is None
    assert inc.escalation_level is L.IT_MANAGER


def test_a_late_first_check_jumps_to_the_right_level_and_is_capped():
    assert level(make_incident_in(S.ASSIGNED), at(30)) is L.IT_MANAGER   # 25 minutes overdue
    assert level(make_incident_in(S.ASSIGNED), at(500)) is L.IT_MANAGER


def test_it_only_applies_to_a_p1_incident_still_waiting_for_acknowledgement():
    p2 = make_incident_in(S.ASSIGNED)
    p2.change_priority(make_admin(), at(1), Priority.P2, "Lower impact", make_tracker())
    assert level(p2, at(60)) is None                                     # not P1
    assert level(make_incident_in(S.ACKNOWLEDGED), at(60)) is None       # already acknowledged
    assert level(make_incident_in(S.CLASSIFIED), at(60)) is None         # nobody assigned yet
    assert level(make_incident(), at(60)) is None                        # not classified
    no_tracker = Incident.restore(dataclasses.replace(make_incident_in(S.ASSIGNED).snapshot(), sla_tracker=None))
    assert level(no_tracker, at(60)) is None


def test_a_manual_escalation_is_respected():
    inc = make_incident_in(S.ASSIGNED)
    inc.escalate(make_admin(), at(6), EscalationDecision(L.SYSTEM_ADMIN, AdminLevel.SYSTEM_ADMIN, "Manual"))
    assert level(inc, at(6)) is None and level(inc, at(15)) is None      # targets TEAM_LEAD, SYSTEM_ADMIN
    assert level(inc, at(25)) is L.IT_MANAGER


def test_evaluate_is_pure_and_its_decision_is_accepted_by_the_incident():
    seen = []

    class Recorder(IncidentObserver):
        def on_event(self, event):
            seen.append(event)

    inc = make_incident_in(S.ASSIGNED)
    inc.add_observer(Recorder())
    before = inc.snapshot()
    decision = POLICY.evaluate(inc, at(7))
    assert inc.snapshot() == before
    inc.escalate(SYSTEM, at(7), decision)
    assert inc.escalation_level is L.TEAM_LEAD
    assert seen[0].description == f"Escalated to TEAM_LEAD: {decision.reason}"
