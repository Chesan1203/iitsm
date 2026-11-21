"""Composition root for real mode: the one place where everything is connected.

    Database -> repositories -> services (+ observers, channels, jobs) -> Container

`assemble_container` does the connecting for any set of repositories (the real SQLite ones, or
the in-memory fakes the tests use). `build_real_container` adds the real database, seeds demo
data on first start and starts the background scheduler. This module is the only one in
`services` allowed to import `persistence`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.intelligence.duplicate_detector import DuplicateDetector
from app.domain.intelligence.escalation_policy import EscalationPolicy
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.strategies.assignment import (
    LoadBasedAssignment, SkillBasedAssignment, WeightedRecommendationStrategy,
)
from app.domain.strategies.priority import RuleBasedPriorityStrategy, WeightedScorePriorityStrategy
from app.domain.time_provider import SimulatedTimeProvider, SystemTimeProvider, TimeProvider
from app.persistence.database import Database
from app.persistence.seeder import DemoDataSeeder
from app.persistence.sqlite_audit_repository import SqliteAuditRepository
from app.persistence.sqlite_category_repository import SqliteCategoryRepository
from app.persistence.sqlite_incident_repository import SqliteIncidentRepository
from app.persistence.sqlite_notification_repository import SqliteNotificationRepository
from app.persistence.sqlite_report_repository import SqliteReportRepository
from app.persistence.sqlite_service_repository import SqliteServiceRepository
from app.persistence.sqlite_settings_repository import SqliteSettingsRepository
from app.persistence.sqlite_sla_event_repository import SqliteSlaEventRepository
from app.persistence.sqlite_sla_policy_repository import SqliteSlaPolicyRepository
from app.persistence.sqlite_user_repository import SqliteUserRepository
from app.ports.container import Container
from app.ports.repositories import (
    AuditRepository, CategoryRepository, IncidentRepository, NotificationRepository,
    ReportRepository, ServiceRepository, SettingsRepository, SlaEventRepository,
    SlaPolicyRepository, UserRepository,
)
from app.services.channels.in_app_channel import InAppChannel
from app.services.channels.simulated_email_channel import SimulatedEmailChannel
from app.services.impl.admin_service import AdminServiceImpl
from app.services.impl.auth_service import AuthServiceImpl
from app.services.impl.incident_service import IncidentServiceImpl
from app.services.impl.lookup_service import LookupServiceImpl
from app.services.impl.notification_service import NotificationServiceImpl
from app.services.impl.report_service import ReportServiceImpl
from app.services.impl.strategy_registry import (
    ASSIGNMENT_SETTING, PRIORITY_SETTING, StrategyRegistry,
)
from app.services.impl.user_factory import UserFactory
from app.services.jobs.escalation_job import EscalationJob
from app.services.jobs.scheduler import JobScheduler
from app.services.jobs.sla_monitor_job import SlaMonitorJob
from app.services.observers.audit_observer import AuditObserver
from app.services.observers.notification_observer import NotificationObserver
from app.services.observers.observer_registrar import ObserverRegistrar
from app.services.security.access_policy import AccessPolicy
from app.services.security.password_hasher import PasswordHasher

logger = logging.getLogger(__name__)


class Repositories(Protocol):
    """Anything with these ten attributes can be assembled (SQLite repositories or fakes)."""
    users: UserRepository
    categories: CategoryRepository
    services: ServiceRepository
    policies: SlaPolicyRepository
    incidents: IncidentRepository
    audits: AuditRepository
    notifications: NotificationRepository
    sla_events: SlaEventRepository
    settings: SettingsRepository
    reports: ReportRepository


class SqliteRepositories:
    """The real repositories, all sharing one Database."""

    def __init__(self, db: Database):
        self.users = SqliteUserRepository(db)
        self.categories = SqliteCategoryRepository(db)
        self.services = SqliteServiceRepository(db)
        self.policies = SqliteSlaPolicyRepository(db)
        self.incidents = SqliteIncidentRepository(db)
        self.audits = SqliteAuditRepository(db)
        self.notifications = SqliteNotificationRepository(db)
        self.sla_events = SqliteSlaEventRepository(db)
        self.settings = SqliteSettingsRepository(db)
        self.reports = SqliteReportRepository(db)


class RealContainer(Container):
    """The six services the web layer uses, plus the parts that need managing."""

    def __init__(self, *, time_provider: TimeProvider, sla_job: SlaMonitorJob,
                 escalation_job: EscalationJob, scheduler: JobScheduler, **services):
        super().__init__(**services)
        self.time_provider = time_provider
        self.sla_job = sla_job
        self.escalation_job = escalation_job
        self.scheduler = scheduler

    def close(self) -> None:
        """Stop the background scheduler (safe to call more than once)."""
        self.scheduler.stop()


def assemble_container(repos: Repositories, *, time_provider: TimeProvider,
                       email_log_path: str | Path, hasher: PasswordHasher | None = None) -> RealContainer:
    """Create every collaborator once and hand each its dependencies through its constructor.
    Nothing here starts a thread or touches the database."""
    hasher = hasher or PasswordHasher()
    access = AccessPolicy()
    factory = UserFactory(hasher)
    calculator = SlaCalculator()

    priority = StrategyRegistry(repos.settings, PRIORITY_SETTING,
                                [WeightedScorePriorityStrategy(), RuleBasedPriorityStrategy()],
                                "weighted_score")
    assignment = StrategyRegistry(repos.settings, ASSIGNMENT_SETTING,
                                  [SkillBasedAssignment(), LoadBasedAssignment(),
                                   WeightedRecommendationStrategy()], "skill_based")

    channels = [InAppChannel(repos.notifications, time_provider),
                SimulatedEmailChannel(email_log_path, time_provider)]
    registrar = ObserverRegistrar([AuditObserver(repos.audits),
                                   NotificationObserver(repos.users, channels)])

    sla_job = SlaMonitorJob(repos.incidents, repos.sla_events, calculator, time_provider, registrar)
    escalation_job = EscalationJob(repos.incidents, EscalationPolicy(), time_provider, registrar)

    return RealContainer(
        time_provider=time_provider, sla_job=sla_job, escalation_job=escalation_job,
        scheduler=JobScheduler(sla_job.run_once, escalation_job.run_once),
        auth=AuthServiceImpl(repos.users, hasher, factory),
        incidents=IncidentServiceImpl(
            repos.incidents, repos.users, repos.categories, repos.services, repos.policies,
            repos.audits, priority, assignment, LoadBasedAssignment(),
            WeightedRecommendationStrategy(), calculator, DuplicateDetector(), time_provider,
            registrar, access),
        lookup=LookupServiceImpl(repos.services, repos.categories, repos.users, access),
        admin=AdminServiceImpl(
            repos.users, repos.services, repos.categories, repos.policies, factory, priority,
            assignment, time_provider, access, sla_job.run_once, escalation_job.run_once),
        reports=ReportServiceImpl(repos.reports, repos.audits, repos.incidents,
                                  CorrelationDetector(), time_provider, access),
        notifications=NotificationServiceImpl(repos.notifications, access))


def build_real_container(settings: Settings) -> RealContainer:
    """Real mode: SQLite database, demo data on first start, background scheduler."""
    db = Database(settings.DATABASE_PATH)
    db.initialise()                                    # creates the data folder and tables
    repos = SqliteRepositories(db)
    clock = SimulatedTimeProvider() if settings.SIMULATED_TIME else SystemTimeProvider()
    container = assemble_container(repos, time_provider=clock, email_log_path=settings.EMAIL_LOG_PATH)

    if settings.SEED_DEMO_DATA:
        seeder = DemoDataSeeder(repos.users, repos.categories, repos.services, repos.policies,
                                repos.incidents, repos.audits, repos.notifications,
                                repos.sla_events, clock)
        logger.info("Checking demo data (first start on an empty database takes about 10 seconds)")
        if seeder.seed_if_empty():
            logger.info("Demo data created. Logins: admin1, tech1, emp1 ... (password in docs/demo_data.md)")
    if settings.ENABLE_SCHEDULER:                      # after seeding, so jobs never see half-seeded data
        container.scheduler.start()
    return container
