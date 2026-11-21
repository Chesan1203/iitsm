from types import SimpleNamespace

import pytest

from app.domain.intelligence.duplicate_detector import DuplicateDetector
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.strategies.assignment import (
    LoadBasedAssignment,
    SkillBasedAssignment,
    WeightedRecommendationStrategy,
)
from app.domain.strategies.priority import (
    RuleBasedPriorityStrategy,
    WeightedScorePriorityStrategy,
)
from app.services.channels.in_app_channel import InAppChannel
from app.services.impl.incident_service import IncidentServiceImpl
from app.services.impl.strategy_registry import (
    ASSIGNMENT_SETTING,
    PRIORITY_SETTING,
    StrategyRegistry,
)
from app.services.impl.user_factory import UserFactory
from app.services.observers.audit_observer import AuditObserver
from app.services.observers.notification_observer import NotificationObserver
from app.services.observers.observer_registrar import ObserverRegistrar
from app.services.security.access_policy import AccessPolicy
from app.services.security.password_hasher import PasswordHasher

from .fakes import FakeRepositories
from .helpers import T0, ManualTime, RecordingChannel, make_world


@pytest.fixture(scope="session")
def hasher() -> PasswordHasher:
    return PasswordHasher(rounds=4)            # bcrypt's minimum: fast tests, same code path


@pytest.fixture
def factory(hasher) -> UserFactory:
    return UserFactory(hasher)


@pytest.fixture
def repos() -> FakeRepositories:
    return FakeRepositories()


@pytest.fixture
def world(repos):
    return make_world(repos)


@pytest.fixture
def stack(repos, world, assignment_registry, priority_registry):
    """The incident service wired to the fakes, a controllable clock, both observers and a
    recording notification channel. Shared by the incident-service and job tests."""
    clock, recording = ManualTime(T0), RecordingChannel()
    notifier = NotificationObserver(repos.users, [InAppChannel(repos.notifications, clock), recording])
    registrar = ObserverRegistrar([AuditObserver(repos.audits), notifier])
    service = IncidentServiceImpl(
        repos.incidents, repos.users, repos.categories, repos.services, repos.policies, repos.audits,
        priority_registry, assignment_registry, LoadBasedAssignment(), WeightedRecommendationStrategy(),
        SlaCalculator(), DuplicateDetector(), clock, registrar, AccessPolicy())
    return SimpleNamespace(svc=service, clock=clock, rec=recording, w=world, repos=repos,
                           registrar=registrar, assignments=assignment_registry,
                           priorities=priority_registry)


@pytest.fixture
def priority_registry(repos) -> StrategyRegistry:
    return StrategyRegistry(repos.settings, PRIORITY_SETTING,
                            [WeightedScorePriorityStrategy(), RuleBasedPriorityStrategy()],
                            "weighted_score")


@pytest.fixture
def assignment_registry(repos) -> StrategyRegistry:
    return StrategyRegistry(repos.settings, ASSIGNMENT_SETTING,
                            [SkillBasedAssignment(), LoadBasedAssignment(), WeightedRecommendationStrategy()],
                            "skill_based")
