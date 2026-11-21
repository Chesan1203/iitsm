"""Web tests run the REAL services (assembled over in-memory fakes) behind the real app, so the
pages are tested against genuine behaviour rather than hand-written stand-ins."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.enums import AdminLevel, Level, Role
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.time_provider import SimulatedTimeProvider
from app.main import create_app
from app.ports.dto import CreateUserRequest
from app.services.impl.user_factory import UserFactory
from app.services.security.password_hasher import PasswordHasher
from app.services.wiring import assemble_container
from tests.services.fakes import FakeRepositories
from tests.services.helpers import ManualTime, default_policy

PASSWORD = "Password@123"


def make_site(tmp_path, clock):
    """Everything a web test needs: the app, its container, the fakes and the cast of users
    (all with the password above)."""
    repos = FakeRepositories()
    hasher = PasswordHasher(rounds=4)
    container = assemble_container(repos, time_provider=clock, email_log_path=tmp_path / "emails.log",
                                   hasher=hasher)
    factory = UserFactory(hasher)

    def person(username, role, **extra):
        return repos.users.save(factory.create(CreateUserRequest(
            username=username, full_name=username.capitalize(), email=f"{username}@x.com",
            password=PASSWORD, role=role, **extra)))

    cast = SimpleNamespace(
        emp1=person("emp1", Role.EMPLOYEE, department="Finance"),
        emp2=person("emp2", Role.EMPLOYEE),
        tech1=person("tech1", Role.TECHNICIAN, skills=("Database",), experience_years=4),
        tech2=person("tech2", Role.TECHNICIAN, skills=("Network",), experience_years=6),
        admin1=person("admin1", Role.ADMINISTRATOR, admin_level=AdminLevel.TEAM_LEAD),
        admin2=person("admin2", Role.ADMINISTRATOR, admin_level=AdminLevel.SYSTEM_ADMIN),
        admin3=person("admin3", Role.ADMINISTRATOR, admin_level=AdminLevel.IT_MANAGER))
    repos.policies.save(default_policy())
    category = repos.categories.save(Category("Database", "Database issues", "Database"))
    service = repos.services.save(ITService("Payment", "Payments", Level.HIGH))

    app = create_app(Settings(ITSM_MODE="stub", ENABLE_SCHEDULER=False, SEED_DEMO_DATA=False,
                              DATABASE_PATH=str(tmp_path / "unused.db"), EMAIL_LOG_PATH=str(tmp_path / "e.log")))
    app.state.container = container                       # the real services over fakes
    return SimpleNamespace(app=app, container=container, repos=repos, clock=clock, cast=cast,
                           category=category, service=service)


@pytest.fixture
def site(tmp_path):
    """The app with a clock the test controls (so the demo controls are switched off)."""
    return make_site(tmp_path, ManualTime())


@pytest.fixture
def sim_site(tmp_path):
    """The app with the simulated demo clock (starts at the real time, can be moved forward)."""
    return make_site(tmp_path, SimulatedTimeProvider())


def login(site, username, password=PASSWORD) -> TestClient:
    """A browser-like client that is signed in (cookies are kept between requests)."""
    client = TestClient(site.app, follow_redirects=False)
    response = client.post("/login", data={"username": username, "password": password})
    assert response.status_code == 303, response.text
    return client


@pytest.fixture
def anonymous(site):
    return TestClient(site.app, follow_redirects=False)
