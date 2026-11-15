import dataclasses

import pytest

from app.domain.enums import AdminLevel, Level, Priority, Role
from app.domain.exceptions import InvalidInputError, MissingSlaConfigurationError
from app.domain.models._validation import (
    optional_text, require_int_between, require_int_min, require_text,
)
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.models.snapshot import IncidentSnapshot
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.user import Administrator, Employee, Technician
from app.domain.observer import IncidentObserver
from tests.domain.helpers import T0, make_incident_in
from app.domain.enums import IncidentStatus as S

H = "hash"


def test_user_behaviour_and_description():
    emp = Employee("emp1", "Asha Rao", "a@x.com", H, "Finance", id=1)
    assert emp.describe() == "Employee Asha Rao (Finance)" and emp.role is Role.EMPLOYEE
    assert Employee("e2", "No Dept", "n@x.com", H, None).department == ""
    assert Employee("e3", "No Dept", "n@x.com", H).describe() == "Employee No Dept"
    emp.deactivate()
    assert not emp.active
    emp.activate()
    assert emp.active

    tech = Technician("t1", "Ravi K", "r@x.com", H, {"Database"}, 4, id=2)
    assert tech.describe() == "Technician Ravi K" and tech.role is Role.TECHNICIAN
    tech.set_available(False)
    assert not tech.available
    tech.set_available(True)
    assert tech.available and tech.skills == frozenset({"Database"})

    admin = Administrator("a1", "Meera N", "m@x.com", H, AdminLevel.IT_MANAGER, id=3)
    assert admin.describe() == "Administrator Meera N (IT_MANAGER)" and admin.admin_level is AdminLevel.IT_MANAGER
    assert "Employee(id=1" in repr(emp) and "Technician(id=2" in repr(tech)


def test_users_are_hashable_and_comparable_by_value():
    a = Employee("emp1", "Asha", "a@x.com", H, id=1)
    b = Employee("emp1", "Asha", "a@x.com", H, id=1)
    assert len({a, b}) == 1 and a == b
    assert a != Technician("emp1", "Asha", "a@x.com", H, id=1) and a != "emp1"
    for blank in (dict(full_name=" "), dict(email=""), dict(password_hash=None)):
        fields = dict(username="u", full_name="U", email="u@x.com", password_hash=H)
        fields.update(blank)
        with pytest.raises(InvalidInputError):
            Employee(**fields)
    with pytest.raises(InvalidInputError):
        Employee("u", "U", "u@x.com", H, 42)                         # department must be text
    with pytest.raises(InvalidInputError):
        Employee("u", "U", "u@x.com", H, id="x")


def test_service_and_category_validation_and_value_semantics():
    svc = ITService("Payment", None, Level.HIGH, 3, id=1)
    assert (svc.name, svc.description, svc.business_criticality, svc.sla_policy_id, svc.active) == (
        "Payment", "", Level.HIGH, 3, True)
    assert svc == ITService("Payment", "", Level.HIGH, 3, id=1) and len({svc, ITService("Payment", "", Level.HIGH, 3, id=1)}) == 1
    assert svc != ITService("Payment", "", Level.LOW, 3, id=1) and svc != "Payment"
    assert "Payment" in repr(svc)
    for bad in (dict(name=" "), dict(business_criticality=3), dict(sla_policy_id=0), dict(sla_policy_id="x")):
        with pytest.raises(InvalidInputError):
            ITService(**{**dict(name="S", description="d", business_criticality=Level.LOW), **bad})

    cat = Category("Database", None, "Database", False, id=2)
    assert (cat.name, cat.description, cat.required_skill, cat.active) == ("Database", "", "Database", False)
    assert cat == Category("Database", "", "Database", False, id=2) and cat != Category("Database", "", "SQL", False, id=2)
    assert len({cat, Category("Database", "", "Database", False, id=2)}) == 1 and "Database" in repr(cat)
    assert cat != "Database"
    for bad in (dict(name=""), dict(required_skill="  ")):
        with pytest.raises(InvalidInputError):
            Category(**{**dict(name="C", description="d", required_skill="s"), **bad})


def test_sla_policy_and_target():
    for bad in ((0, 5), (5, 0), (True, 5), (5, 1.5)):
        with pytest.raises(InvalidInputError):
            SlaTarget(*bad)
    policy = SlaPolicy("Default", True, {Priority.P1: SlaTarget(5, 30)}, id=1)
    assert policy.name == "Default" and policy.is_default and "Default" in repr(policy)
    assert policy == SlaPolicy("Default", True, {Priority.P1: SlaTarget(5, 30)}, id=1)
    assert len({policy, SlaPolicy("Default", True, {Priority.P1: SlaTarget(5, 30)}, id=1)}) == 1
    assert policy != SlaPolicy("Default", False, {Priority.P1: SlaTarget(5, 30)}, id=1) and policy != "x"
    assert SlaPolicy("Empty").targets == {}
    for bad_targets in ({"P1": SlaTarget(5, 30)}, {Priority.P1: (5, 30)}):
        with pytest.raises(InvalidInputError):
            SlaPolicy("Bad", False, bad_targets)
    with pytest.raises(MissingSlaConfigurationError):
        SlaPolicy("Empty").target_for(Priority.P2)
    with pytest.raises(InvalidInputError):
        SlaPolicy(" ")


def test_snapshot_defaults_and_note_normalisation():
    inc = make_incident_in(S.NEW)
    snap = inc.snapshot()
    assert snap.notes == () and snap.priority is None and snap.sla_tracker is None
    as_list = dataclasses.replace(snap, notes=[])
    assert isinstance(as_list.notes, tuple) and as_list == snap
    assert isinstance(IncidentSnapshot, type)


def test_validation_helpers():
    assert require_text("  x  ", "f") == "x" and optional_text(None, "f") == "" and optional_text(" y ", "f") == "y"
    assert require_int_min(3, 1, "f") == 3 and require_int_between(5, 1, 5, "f") == 5
    for call in (lambda: optional_text(5, "f"), lambda: require_int_between(6, 1, 5, "f"),
                 lambda: require_int_between(False, 0, 5, "f"), lambda: require_int_min(0, 1, "f")):
        with pytest.raises(InvalidInputError):
            call()


def test_observer_interface_is_abstract():
    with pytest.raises(TypeError):
        IncidentObserver()


def test_remaining_small_behaviours():
    from app.domain.models.user import User
    a = Administrator("a1", "Meera N", "m@x.com", H, AdminLevel.TEAM_LEAD, id=1)
    assert a == Administrator("a1", "Meera N", "m@x.com", H, AdminLevel.TEAM_LEAD, id=1)
    assert a != Administrator("a1", "Meera N", "m@x.com", H, AdminLevel.IT_MANAGER, id=1)
    assert User.system().describe() == "System"
    inc = make_incident_in(S.ASSIGNED)
    assert "INC-1102" in repr(inc) and "ASSIGNED" in repr(inc)
    assert "ON_TRACK" in repr(inc.sla_tracker)
    from tests.domain.helpers import make_incident
    assert "unsaved" in repr(make_incident())
