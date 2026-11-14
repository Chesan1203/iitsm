"""Repository interfaces. Persistence implements them; services consume them.

Conventions
- find_* returns None (or an empty list) when nothing matches. Services turn None
  into a NotFoundError.
- save inserts when the object's id is None and updates otherwise, and returns the
  saved object with its id filled in.
- Incidents are loaded without observers. Services re-attach them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.enums import AdminLevel, Role, SlaEventType
from app.domain.models.audit import AuditRecord
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent, SlaPolicy
from app.domain.models.user import User
from app.ports.dto import (
    AuditFilter, CountRow, IncidentSearchCriteria, OverviewReport, SlaViolationRow, WorkloadRow,
)


class UserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> User: ...
    @abstractmethod
    def find_by_id(self, id: int) -> User | None: ...
    @abstractmethod
    def find_by_username(self, username: str) -> User | None: ...
    @abstractmethod
    def find_all(self) -> list[User]: ...
    @abstractmethod
    def find_by_role(self, role: Role) -> list[User]: ...
    @abstractmethod
    def find_admins_by_level(self, level: AdminLevel) -> list[User]: ...


class ServiceRepository(ABC):
    @abstractmethod
    def save(self, service: ITService) -> ITService: ...
    @abstractmethod
    def find_by_id(self, id: int) -> ITService | None: ...
    @abstractmethod
    def find_all(self) -> list[ITService]: ...
    @abstractmethod
    def exists_by_name(self, name: str) -> bool: ...


class CategoryRepository(ABC):
    @abstractmethod
    def save(self, category: Category) -> Category: ...
    @abstractmethod
    def find_by_id(self, id: int) -> Category | None: ...
    @abstractmethod
    def find_all(self) -> list[Category]: ...


class SlaPolicyRepository(ABC):
    @abstractmethod
    def save(self, policy: SlaPolicy) -> SlaPolicy: ...
    @abstractmethod
    def find_by_id(self, id: int) -> SlaPolicy | None: ...
    @abstractmethod
    def find_default(self) -> SlaPolicy | None: ...
    @abstractmethod
    def find_all(self) -> list[SlaPolicy]: ...


class IncidentRepository(ABC):
    @abstractmethod
    def save(self, incident: Incident) -> Incident:
        """On first save assigns id and ticket_number (INC-1001, ...)."""
    @abstractmethod
    def find_by_id(self, id: int) -> Incident | None: ...
    @abstractmethod
    def find_by_ticket(self, ticket_number: str) -> Incident | None: ...
    @abstractmethod
    def search(self, criteria: IncidentSearchCriteria) -> list[Incident]: ...
    @abstractmethod
    def find_open(self) -> list[Incident]:
        """Every incident whose status is not CLOSED."""
    @abstractmethod
    def find_unacknowledged(self) -> list[Incident]:
        """Every incident whose status is ASSIGNED."""
    @abstractmethod
    def find_recent_by_service(self, service_id: int, since: datetime) -> list[Incident]: ...
    @abstractmethod
    def find_recent_by_reporter(self, reporter_id: int, since: datetime) -> list[Incident]: ...
    @abstractmethod
    def count_active_by_technician(self, technician_id: int) -> int:
        """Incidents in ASSIGNED, ACKNOWLEDGED or IN_PROGRESS."""
    @abstractmethod
    def count_resolved_by_technician_on_service(self, technician_id: int, service_id: int) -> int:
        """Incidents in RESOLVED, VERIFIED or CLOSED."""


class AuditRepository(ABC):
    @abstractmethod
    def save(self, record: AuditRecord) -> AuditRecord: ...
    @abstractmethod
    def find_by_incident(self, incident_id: int) -> list[AuditRecord]: ...
    @abstractmethod
    def search(self, audit_filter: AuditFilter) -> list[AuditRecord]: ...


class NotificationRepository(ABC):
    @abstractmethod
    def save(self, notification: Notification) -> Notification: ...
    @abstractmethod
    def find_by_recipient(self, user_id: int, limit: int) -> list[Notification]: ...
    @abstractmethod
    def count_unread(self, user_id: int) -> int: ...
    @abstractmethod
    def mark_read(self, notification_id: int) -> None: ...
    @abstractmethod
    def mark_all_read(self, user_id: int) -> None: ...


class SlaEventRepository(ABC):
    @abstractmethod
    def save(self, event: SlaEvent) -> SlaEvent: ...
    @abstractmethod
    def find_by_incident(self, incident_id: int) -> list[SlaEvent]: ...
    @abstractmethod
    def exists(self, incident_id: int, event_type: SlaEventType) -> bool: ...


class SettingsRepository(ABC):
    @abstractmethod
    def get(self, key: str, default: str | None = None) -> str | None: ...
    @abstractmethod
    def put(self, key: str, value: str) -> None: ...


class ReportRepository(ABC):
    @abstractmethod
    def get_overview(self) -> OverviewReport: ...
    @abstractmethod
    def get_technician_workload(self) -> list[WorkloadRow]: ...
    @abstractmethod
    def get_service_analysis(self) -> list[CountRow]: ...
    @abstractmethod
    def get_category_analysis(self) -> list[CountRow]: ...
    @abstractmethod
    def get_sla_violations(self) -> list[SlaViolationRow]: ...
