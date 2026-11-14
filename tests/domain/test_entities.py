from datetime import datetime

import pytest

from app.domain.enums import (
    AdminLevel, EscalationLevel, IncidentStatus, Level, NoteType, Priority, Role, SlaStatus,
)
from app.domain.exceptions import InvalidInputError, MissingSlaConfigurationError
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution, SlaTracker
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.user import Administrator, Employee, Technician, User

T0 = datetime(2026, 11, 14, 10, 5)
H = "hash"


def make_world():
    emp = Employee("emp1", "Asha Rao", "asha@x.com", H, "Finance", id=1)
    tech = Technician("tech1", "Ravi K", "ravi@x.com", H, {"Database"}, 4, id=2)
    cat = Category("Database", "DB issues", "Database", id=1)
    svc = ITService("Payment", "Payments", Level.HIGH, id=1)
    return emp, tech, cat, svc


def make_incident():
    emp, _, cat, svc = make_world()
    return Incident("Payment down", "Cannot pay", emp, cat, svc, Level.HIGH, Level.HIGH, 120, T0)


def test_user_is_abstract():
    with pytest.raises(TypeError):
        User("u", "U", "u@x.com", H, Role.EMPLOYEE)


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_blank_username_rejected(bad):
    with pytest.raises(InvalidInputError) as e:
        Employee(bad, "A", "a@x.com", H)
    assert e.value.field == "username"


def test_technician_validation():
    with pytest.raises(InvalidInputError):
        Technician("t", "T", "t@x.com", H, {"a"}, experience_years=-1)
    with pytest.raises(InvalidInputError):
        Technician("t", "T", "t@x.com", H, "Database")      # a bare string is a bug
    with pytest.raises(InvalidInputError):
        Technician("t", "T", "t@x.com", H, {"a"}, max_workload=0)
    t = Technician("t", "T", "t@x.com", H, {"a"})
    assert t.max_workload == 5 and isinstance(t.skills, frozenset) and t.available


def test_administrator_requires_level():
    with pytest.raises(InvalidInputError):
        Administrator("a", "A", "a@x.com", H, "TEAM_LEAD")
    assert Administrator("a", "A", "a@x.com", H, AdminLevel.TEAM_LEAD).role is Role.ADMINISTRATOR


def test_system_user():
    s = User.system()
    assert s.id == 0 and s.is_system and s is User.system()


def test_id_is_write_once():
    e = Employee("e", "E", "e@x.com", H)
    assert e.id is None
    e.assign_id(7)
    assert e.id == 7
    with pytest.raises(InvalidInputError):
        e.assign_id(8)


def test_value_equality_for_entities():
    a = Employee("e", "E", "e@x.com", H, "IT", id=3)
    b = Employee("e", "E", "e@x.com", H, "IT", id=3)
    assert a == b and a is not b
    b.deactivate()
    assert a != b


def test_feedback_rating_bounds():
    for bad in (0, 6, True, 2.5):
        with pytest.raises(InvalidInputError):
            Feedback(bad, "x", T0)
    assert Feedback(1, "", T0).rating == 1 and Feedback(5, "", T0).rating == 5


def test_sla_policy_missing_target():
    policy = SlaPolicy("Default", True, {Priority.P1: SlaTarget(5, 30)})
    assert policy.target_for(Priority.P1).resolution_minutes == 30
    with pytest.raises(MissingSlaConfigurationError):
        policy.target_for(Priority.P4)
    policy.targets.clear()                      # a copy: must not affect the policy
    assert Priority.P1 in policy.targets


def test_incident_constructor_defaults():
    inc = make_incident()
    assert inc.status is IncidentStatus.NEW and inc.priority is None and inc.sla_tracker is None
    assert inc.is_open and not inc.is_active and inc.id is None and inc.ticket_number is None
    assert inc.escalation_level is EscalationLevel.TECHNICIAN


def test_incident_constructor_validation():
    emp, _, cat, svc = make_world()
    with pytest.raises(InvalidInputError):
        Incident("", "d", emp, cat, svc, Level.LOW, Level.LOW, 1, T0)
    with pytest.raises(InvalidInputError):
        Incident("t", "d", emp, cat, svc, Level.LOW, Level.LOW, 0, T0)
    with pytest.raises(InvalidInputError):
        Incident("t", "d", emp, cat, svc, 2, Level.LOW, 1, T0)


def test_incident_identity_is_write_once():
    inc = make_incident()
    inc.assign_identity(42, "INC-1042")
    assert (inc.id, inc.ticket_number) == (42, "INC-1042")
    with pytest.raises(InvalidInputError):
        inc.assign_identity(43, "INC-1043")


def test_snapshot_restore_roundtrip_full_incident():
    emp, tech, cat, svc = make_world()
    note = InvestigationNote(id=1, author=tech, note_type=NoteType.INVESTIGATION,
                             text="Checked DB logs", created_at=T0)
    snap = IncidentSnapshot(
        id=5, ticket_number="INC-1005", title="Payment down", description="Cannot pay",
        reporter=emp, category=cat, affected_service=svc, impact=Level.HIGH, urgency=Level.HIGH,
        affected_users=120, priority=Priority.P1, priority_score=27, status=IncidentStatus.RESOLVED,
        created_at=T0, assigned_technician=tech, assigned_at=T0, acknowledged_at=T0,
        resolved_at=T0, escalation_level=EscalationLevel.TEAM_LEAD,
        possible_duplicate_of="INC-1001", notes=[note],
        resolution=Resolution("Restarted DB", "Pool exhausted", tech, T0),
        feedback=Feedback(4, "ok", T0),
        sla_tracker=SlaTracker(T0, T0, response_warned=True, status=SlaStatus.WARNING),
    )
    inc = Incident.restore(snap)
    assert inc.snapshot() == snap
    assert inc.status is IncidentStatus.RESOLVED and inc.notes == [note]
    assert inc.snapshot().sla_tracker is not inc.snapshot().sla_tracker   # copies, no aliasing
    assert inc.is_open and not inc.is_active


def test_notes_property_is_a_copy():
    inc = make_incident()
    inc.notes.append("junk")
    assert inc.notes == []
