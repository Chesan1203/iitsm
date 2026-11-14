"""Service interfaces used by the web layer.

Every method except login and register_employee takes the acting user first.
Services raise the exceptions from app.domain.exceptions; they never return error
codes. Methods that change an incident return the updated Incident.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.enums import Priority
from app.domain.models.audit import AuditRecord
from app.domain.models.candidates import RankedTechnician
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaPolicy
from app.domain.models.user import Technician, User
from app.ports.dto import (
    AuditFilter, CategoryRequest, CountRow, CreateIncidentRequest, CreateUserRequest,
    IncidentSearchCriteria, OverviewReport, RegisterRequest, ServiceRequest, SlaPolicyRequest,
    SlaViolationRow, WorkloadRow,
)

if TYPE_CHECKING:
    from app.domain.intelligence.correlation_detector import CorrelationGroup


class AuthService(ABC):
    @abstractmethod
    def login(self, username: str, password: str) -> User: ...
    @abstractmethod
    def register_employee(self, request: RegisterRequest) -> User: ...
    @abstractmethod
    def get_user(self, user_id: int) -> User | None:
        """Used by the web layer to reload the logged-in user from the session."""


class IncidentService(ABC):
    @abstractmethod
    def create_incident(self, actor: User, request: CreateIncidentRequest) -> Incident: ...
    @abstractmethod
    def get_incident(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def search(self, actor: User, criteria: IncidentSearchCriteria) -> list[Incident]:
        """Scoped by role: employees see their own, technicians theirs, admins all."""
    @abstractmethod
    def assign(self, actor: User, incident_id: int, technician_id: int) -> Incident:
        """Also handles reassignment."""
    @abstractmethod
    def auto_assign(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def recommend_technicians(self, actor: User, incident_id: int) -> list[RankedTechnician]: ...
    @abstractmethod
    def acknowledge(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def start_investigation(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def add_note(self, actor: User, incident_id: int, text: str) -> Incident: ...
    @abstractmethod
    def request_info(self, actor: User, incident_id: int, question: str) -> Incident: ...
    @abstractmethod
    def respond_to_info_request(self, actor: User, incident_id: int, answer: str) -> Incident: ...
    @abstractmethod
    def resolve(self, actor: User, incident_id: int, summary: str, details: str) -> Incident: ...
    @abstractmethod
    def verify(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def reject_resolution(self, actor: User, incident_id: int, reason: str) -> Incident: ...
    @abstractmethod
    def close(self, actor: User, incident_id: int) -> Incident: ...
    @abstractmethod
    def submit_feedback(self, actor: User, incident_id: int, rating: int, comment: str) -> Incident: ...
    @abstractmethod
    def override_priority(self, actor: User, incident_id: int, priority: Priority, reason: str) -> Incident: ...
    @abstractmethod
    def get_audit_trail(self, actor: User, incident_id: int) -> list[AuditRecord]: ...


class LookupService(ABC):
    @abstractmethod
    def list_active_services(self, actor: User) -> list[ITService]: ...
    @abstractmethod
    def list_active_categories(self, actor: User) -> list[Category]: ...
    @abstractmethod
    def list_technicians(self, actor: User) -> list[Technician]: ...


class AdminService(ABC):
    @abstractmethod
    def list_users(self, actor: User) -> list[User]: ...
    @abstractmethod
    def create_user(self, actor: User, request: CreateUserRequest) -> User: ...
    @abstractmethod
    def deactivate_user(self, actor: User, user_id: int) -> User: ...
    @abstractmethod
    def activate_user(self, actor: User, user_id: int) -> User: ...
    @abstractmethod
    def set_technician_availability(self, actor: User, user_id: int, available: bool) -> User: ...
    @abstractmethod
    def list_services(self, actor: User) -> list[ITService]: ...
    @abstractmethod
    def create_service(self, actor: User, request: ServiceRequest) -> ITService: ...
    @abstractmethod
    def update_service(self, actor: User, id: int, request: ServiceRequest) -> ITService: ...
    @abstractmethod
    def list_categories(self, actor: User) -> list[Category]: ...
    @abstractmethod
    def create_category(self, actor: User, request: CategoryRequest) -> Category: ...
    @abstractmethod
    def update_category(self, actor: User, id: int, request: CategoryRequest) -> Category: ...
    @abstractmethod
    def list_sla_policies(self, actor: User) -> list[SlaPolicy]: ...
    @abstractmethod
    def save_sla_policy(self, actor: User, request: SlaPolicyRequest) -> SlaPolicy: ...
    @abstractmethod
    def list_assignment_strategies(self, actor: User) -> list[str]: ...
    @abstractmethod
    def get_assignment_strategy(self, actor: User) -> str: ...
    @abstractmethod
    def set_assignment_strategy(self, actor: User, name: str) -> None: ...
    @abstractmethod
    def list_priority_strategies(self, actor: User) -> list[str]: ...
    @abstractmethod
    def get_priority_strategy(self, actor: User) -> str: ...
    @abstractmethod
    def set_priority_strategy(self, actor: User, name: str) -> None: ...
    @abstractmethod
    def is_time_simulated(self, actor: User) -> bool: ...
    @abstractmethod
    def get_current_time(self, actor: User) -> datetime: ...
    @abstractmethod
    def advance_time(self, actor: User, minutes: int) -> datetime:
        """Returns the new current time."""
    @abstractmethod
    def reset_time(self, actor: User) -> datetime:
        """Returns the new current time."""
    @abstractmethod
    def run_sla_check_now(self, actor: User) -> int:
        """Returns how many SLA events were recorded."""
    @abstractmethod
    def run_escalation_check_now(self, actor: User) -> int:
        """Returns how many incidents were escalated."""


class ReportService(ABC):
    """Administrators only."""

    @abstractmethod
    def overview(self, actor: User) -> OverviewReport: ...
    @abstractmethod
    def technician_workload(self, actor: User) -> list[WorkloadRow]: ...
    @abstractmethod
    def service_analysis(self, actor: User) -> list[CountRow]: ...
    @abstractmethod
    def category_analysis(self, actor: User) -> list[CountRow]: ...
    @abstractmethod
    def sla_violations(self, actor: User) -> list[SlaViolationRow]: ...
    @abstractmethod
    def audit_log(self, actor: User, audit_filter: AuditFilter) -> list[AuditRecord]: ...
    @abstractmethod
    def correlation_groups(self, actor: User) -> list[CorrelationGroup]:
        """Stretch feature."""


class NotificationService(ABC):
    @abstractmethod
    def list_for_user(self, actor: User, limit: int) -> list[Notification]: ...
    @abstractmethod
    def unread_count(self, actor: User) -> int: ...
    @abstractmethod
    def mark_read(self, actor: User, notification_id: int) -> None: ...
    @abstractmethod
    def mark_all_read(self, actor: User) -> None: ...
