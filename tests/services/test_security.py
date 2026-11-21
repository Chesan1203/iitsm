"""P3 T2: password hashing, input rules, user factory, access policy and authentication."""
import pytest

from app.domain.enums import AdminLevel, Role
from app.domain.exceptions import (
    InvalidInputError,
    InvalidLoginError,
    UnauthorizedOperationError,
)
from app.domain.models.user import Administrator, Employee, Technician, User
from app.ports.dto import CreateUserRequest, IncidentSearchCriteria, RegisterRequest
from app.services.impl.auth_service import AuthServiceImpl
from app.services.security.access_policy import AccessPolicy
from app.services.security.input_rules import (
    validate_email,
    validate_password,
    validate_username,
)

from .helpers import assign, classify, new_incident

# ---- password hasher ---------------------------------------------------------------------------

def test_hash_is_salted_one_way_and_verifies(hasher):
    first, second = hasher.hash("Password@123"), hasher.hash("Password@123")
    assert first != second and "Password@123" not in first
    assert hasher.verify("Password@123", first) and hasher.verify("Password@123", second)
    assert not hasher.verify("password@123", first)


def test_verify_never_raises_on_bad_input(hasher):
    assert hasher.verify("x" * 100, hasher.hash("Password@123")) is False     # over bcrypt's 72 bytes
    assert hasher.verify("Password@123", "not-a-bcrypt-hash") is False
    assert hasher.verify("Password@123", "!") is False                        # the system user's hash
    assert hasher.verify(None, hasher.hash("Password@123")) is False


def test_hashing_an_over_long_password_is_an_input_error_not_a_crash(hasher):
    with pytest.raises(InvalidInputError) as caught:
        hasher.hash("é" * 40)                       # 80 bytes
    assert caught.value.field == "password"


# ---- input rules ------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "ab", "a" * 31, "has space", "semi;colon", "émile", None])
def test_bad_usernames_are_rejected_with_the_field_named(bad):
    with pytest.raises(InvalidInputError) as caught:
        validate_username(bad)
    assert caught.value.field == "username"


def test_username_boundaries_and_trimming():
    assert validate_username("abc") == "abc" and validate_username("a" * 30) == "a" * 30
    assert validate_username("  first.last_1 ") == "first.last_1"


def test_password_and_email_rules():
    assert validate_password("12345678")
    for bad in ("1234567", "", None):
        with pytest.raises(InvalidInputError):
            validate_password(bad)
    assert validate_email(" a@b.co ") == "a@b.co"
    for bad in ("plain", "a@b", "a b@c.com", "", None):
        with pytest.raises(InvalidInputError):
            validate_email(bad)


# ---- user factory -----------------------------------------------------------------------------------

def _request(role, **extra):
    base = dict(username="new.user", full_name="New  User", email="n@x.com", password="Password@123")
    return CreateUserRequest(role=role, **{**base, **extra})


def test_factory_builds_the_right_subclass_with_a_hashed_password(factory, hasher):
    emp = factory.create(_request(Role.EMPLOYEE, department="Sales"))
    tech = factory.create(_request(Role.TECHNICIAN, skills=("Network", " Cloud ", ""), experience_years=3, max_workload=4))
    admin = factory.create(_request(Role.ADMINISTRATOR, admin_level=AdminLevel.IT_MANAGER))
    assert (type(emp), type(tech), type(admin)) == (Employee, Technician, Administrator)
    assert emp.department == "Sales" and emp.full_name == "New User"
    assert tech.skills == {"Network", "Cloud"} and tech.max_workload == 4 and tech.available
    assert admin.admin_level is AdminLevel.IT_MANAGER
    assert all(u.password_hash != "Password@123" and hasher.verify("Password@123", u.password_hash)
               for u in (emp, tech, admin))


def test_factory_rejects_administrator_without_level_and_bad_fields(factory):
    with pytest.raises(InvalidInputError) as caught:
        factory.create(_request(Role.ADMINISTRATOR))
    assert caught.value.field == "admin_level"
    with pytest.raises(InvalidInputError):
        factory.create(_request(Role.TECHNICIAN, experience_years=-1))
    with pytest.raises(InvalidInputError):
        factory.create(_request(Role.EMPLOYEE, password="short"))


# ---- authentication ---------------------------------------------------------------------------------

@pytest.fixture
def auth(repos, hasher, factory):
    service = AuthServiceImpl(repos.users, hasher, factory)
    repos.users.save(factory.create(_request(Role.EMPLOYEE, username="alice", full_name="Alice A")))
    return service


def test_login_with_the_right_password_returns_the_user(auth):
    user = auth.login("alice", "Password@123")
    assert user.username == "alice" and user.id is not None
    assert auth.login("  alice ", "Password@123").id == user.id          # surrounding spaces ignored


def test_wrong_password_unknown_user_and_inactive_account_fail_identically(auth, repos):
    errors = []
    for username, password in (("alice", "wrong-password"), ("nobody", "Password@123")):
        with pytest.raises(InvalidLoginError) as caught:
            auth.login(username, password)
        errors.append(caught.value.message)
    alice = repos.users.find_by_username("alice")
    alice.deactivate()
    repos.users.save(alice)
    with pytest.raises(InvalidLoginError) as caught:
        auth.login("alice", "Password@123")                              # correct password, inactive
    errors.append(caught.value.message)
    assert errors == ["Invalid username or password"] * 3


def test_login_with_missing_input_is_an_ordinary_failed_login(auth):
    for username, password in ((None, "x"), ("alice", None), ("", "")):
        with pytest.raises(InvalidLoginError):
            auth.login(username, password)


def test_register_creates_an_employee_with_a_hashed_password(auth, repos, hasher):
    user = auth.register_employee(RegisterRequest("bob_b", "Bob B", "bob@x.com", "Password@123", "HR"))
    stored = repos.users.find_by_id(user.id)
    assert isinstance(stored, Employee) and stored.department == "HR"
    assert stored.password_hash != "Password@123" and hasher.verify("Password@123", stored.password_hash)
    assert auth.login("bob_b", "Password@123").id == user.id


@pytest.mark.parametrize("field,request_", [
    ("username", RegisterRequest("x", "Bob", "b@x.com", "Password@123")),
    ("password", RegisterRequest("bobby", "Bob", "b@x.com", "short")),
    ("email", RegisterRequest("bobby", "Bob", "not-an-email", "Password@123")),
    ("full_name", RegisterRequest("bobby", "  ", "b@x.com", "Password@123")),
    ("username", RegisterRequest("alice", "Alice 2", "a2@x.com", "Password@123")),     # already taken
])
def test_register_rejects_bad_input_naming_the_field(auth, field, request_):
    with pytest.raises(InvalidInputError) as caught:
        auth.register_employee(request_)
    assert caught.value.field == field


def test_register_cannot_be_used_to_become_an_administrator(auth):
    user = auth.register_employee(RegisterRequest("sneaky", "Sneaky", "s@x.com", "Password@123"))
    assert user.role is Role.EMPLOYEE


def test_get_user_returns_active_users_only(auth, repos):
    alice = repos.users.find_by_username("alice")
    assert auth.get_user(alice.id).username == "alice"
    assert auth.get_user(999) is None
    alice.deactivate()
    repos.users.save(alice)
    assert auth.get_user(alice.id) is None


# ---- access policy -------------------------------------------------------------------------------------

def test_require_role_and_require_user(world):
    policy = AccessPolicy()
    assert policy.require_role(world.admin, Role.ADMINISTRATOR) is world.admin
    with pytest.raises(UnauthorizedOperationError):
        policy.require_role(world.reporter, Role.ADMINISTRATOR)
    for bad in (None, User.system(), "someone"):
        with pytest.raises(UnauthorizedOperationError):
            policy.require_user(bad)
    gone = world.repos.users.find_by_id(world.reporter.id)
    gone.deactivate()
    with pytest.raises(UnauthorizedOperationError):
        policy.require_user(gone)


def test_who_can_view_an_incident(world):
    policy = AccessPolicy()
    incident = assign(classify(new_incident(world)), world.tech)
    for allowed in (world.reporter, world.admin, world.tech):
        assert policy.require_can_view(allowed, incident) is allowed
    for denied in (world.other_employee, world.tech2):
        with pytest.raises(UnauthorizedOperationError):
            policy.require_can_view(denied, incident)


def test_search_criteria_are_scoped_by_role_and_conflicts_are_overridden(world):
    policy = AccessPolicy()
    wide = IncidentSearchCriteria(keyword="pay")
    assert policy.scope_criteria(world.reporter, wide).reporter_id == world.reporter.id
    assert policy.scope_criteria(world.tech, wide).technician_id == world.tech.id
    assert policy.scope_criteria(world.admin, wide) == wide
    snooping = IncidentSearchCriteria(reporter_id=world.other_employee.id)
    assert policy.scope_criteria(world.reporter, snooping).reporter_id == world.reporter.id
    assert wide.reporter_id is None                       # the original is never modified
