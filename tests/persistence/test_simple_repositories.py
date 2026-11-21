"""P2 T3 part 1: settings, categories, services, SLA policies and users."""
import pytest

from app.domain.enums import AdminLevel, Level, Priority, Role
from app.domain.exceptions import PersistenceError
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy, SlaTarget
from app.domain.models.user import Employee, User

from .conftest import new_admin, new_employee, new_technician


# ---- settings ----------------------------------------------------------------------

def test_settings_get_returns_default_when_missing(world):
    assert world.settings.get("priority.strategy") is None
    assert world.settings.get("priority.strategy", "weighted") == "weighted"


def test_settings_put_then_get_and_overwrite(world):
    world.settings.put("assignment.strategy", "skill")
    assert world.settings.get("assignment.strategy") == "skill"
    world.settings.put("assignment.strategy", "load")
    assert world.settings.get("assignment.strategy") == "load"


# ---- categories --------------------------------------------------------------------

def test_category_save_assigns_id_and_round_trips(world):
    saved = world.categories.save(Category("Network", "Net issues", "Network"))
    assert saved.id is not None
    assert world.categories.find_by_id(saved.id) == saved


def test_category_second_save_updates_instead_of_inserting(world):
    before = len(world.categories.find_all())
    changed = Category("Database", "Renamed text", "Database", active=False, id=world.category.id)
    world.categories.save(changed)
    assert len(world.categories.find_all()) == before
    assert world.categories.find_by_id(world.category.id) == changed


def test_category_missing_id_gives_none_and_update_of_missing_raises(world):
    assert world.categories.find_by_id(999) is None
    with pytest.raises(PersistenceError):
        world.categories.save(Category("Ghost", "", "x", id=999))


def test_category_duplicate_name_raises_and_leaves_no_id(world):
    duplicate = Category("Database", "again", "Database")
    with pytest.raises(PersistenceError):
        world.categories.save(duplicate)
    assert duplicate.id is None


# ---- services ----------------------------------------------------------------------

def test_service_round_trips_criticality_and_policy_link(world):
    policy = world.policies.save(SlaPolicy("Strict", False, {Priority.P1: SlaTarget(2, 10)}))
    saved = world.services.save(ITService("Database", "DB", Level.MEDIUM, policy.id, False))
    loaded = world.services.find_by_id(saved.id)
    assert loaded == saved
    assert loaded.business_criticality is Level.MEDIUM and loaded.sla_policy_id == policy.id
    assert loaded.active is False


def test_service_update_and_find_all(world):
    world.services.save(ITService("Payment", "New text", Level.LOW, id=world.service.id))
    services = world.services.find_all()
    assert len(services) == 1 and services[0].description == "New text"


def test_service_exists_by_name_ignores_case(world):
    assert world.services.exists_by_name("payment")
    assert world.services.exists_by_name("PAYMENT")
    assert not world.services.exists_by_name("Printer")


def test_service_with_unknown_sla_policy_is_rejected(world):
    with pytest.raises(PersistenceError):
        world.services.save(ITService("Email", "", Level.LOW, sla_policy_id=999))


# ---- SLA policies ------------------------------------------------------------------

def _policy(name="Default", default=True):
    return SlaPolicy(name, default, {Priority.P1: SlaTarget(5, 30), Priority.P2: SlaTarget(15, 120),
                                     Priority.P3: SlaTarget(60, 480), Priority.P4: SlaTarget(240, 1440)})


def test_sla_policy_round_trips_with_all_targets(world):
    saved = world.policies.save(_policy())
    loaded = world.policies.find_by_id(saved.id)
    assert loaded == saved
    assert loaded.target_for(Priority.P1) == SlaTarget(5, 30)


def test_sla_policy_resave_replaces_targets(world):
    saved = world.policies.save(_policy())
    world.policies.save(SlaPolicy("Default", True, {Priority.P1: SlaTarget(1, 2)}, id=saved.id))
    loaded = world.policies.find_by_id(saved.id)
    assert loaded.targets == {Priority.P1: SlaTarget(1, 2)}


def test_sla_policy_find_default_and_find_all(world):
    assert world.policies.find_default() is None
    world.policies.save(_policy("Strict", default=False))
    default = world.policies.save(_policy("Standard", default=True))
    assert world.policies.find_default() == default
    assert [p.name for p in world.policies.find_all()] == ["Strict", "Standard"]


# ---- users -------------------------------------------------------------------------

def test_each_role_round_trips_to_the_right_class_and_equal_object(world):
    for user in (new_employee("e2"), new_technician("t2"), new_admin("a2", AdminLevel.IT_MANAGER)):
        saved = world.users.save(user)
        loaded = world.users.find_by_id(saved.id)
        assert type(loaded) is type(user) and loaded == saved


def test_technician_fields_and_skills_are_preserved(world):
    tech = world.users.save(new_technician("t3", skills={"Cloud", "Security"}, experience=9,
                                           available=False, max_workload=3))
    loaded = world.users.find_by_username("t3")
    assert loaded.skills == {"Cloud", "Security"}
    assert (loaded.experience_years, loaded.available, loaded.max_workload) == (9, False, 3)
    assert loaded == tech


def test_resaving_a_technician_replaces_their_skills(world):
    tech = world.technician
    world.users.save(type(tech)(tech.username, tech.full_name, tech.email, tech.password_hash,
                                {"Storage"}, 2, True, 5, id=tech.id))
    assert world.users.find_by_id(tech.id).skills == {"Storage"}


def test_user_lookups(world):
    assert world.users.find_by_username("emp1") == world.reporter
    assert world.users.find_by_username("nobody") is None
    assert world.users.find_by_id(999) is None
    assert [u.username for u in world.users.find_by_role(Role.TECHNICIAN)] == ["tech1"]
    assert len(world.users.find_all()) == 3


def test_find_admins_by_level(world):
    manager = world.users.save(new_admin("boss", AdminLevel.IT_MANAGER))
    assert world.users.find_admins_by_level(AdminLevel.IT_MANAGER) == [manager]
    assert world.users.find_admins_by_level(AdminLevel.TEAM_LEAD) == [world.admin]
    assert world.users.find_admins_by_level(AdminLevel.SYSTEM_ADMIN) == []


def test_inactive_flag_and_password_hash_survive(world):
    saved = world.users.save(new_employee("gone", active=False))
    loaded = world.users.find_by_id(saved.id)
    assert loaded.active is False and loaded.password_hash == "hash-e"


def test_duplicate_username_raises_and_leaves_no_id(world):
    duplicate = new_employee("emp1")
    with pytest.raises(PersistenceError) as caught:
        world.users.save(duplicate)
    assert "username" in caught.value.message
    assert duplicate.id is None


def test_system_user_is_never_stored(world):
    with pytest.raises(PersistenceError):
        world.users.save(User.system())


def test_updating_a_missing_user_raises(world):
    with pytest.raises(PersistenceError):
        world.users.save(Employee("x", "X", "x@x.com", "h", id=999))
