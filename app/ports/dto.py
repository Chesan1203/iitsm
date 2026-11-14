from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.domain.business_rules import BusinessRules
from app.domain.enums import (
    AdminLevel, IncidentStatus, Level, Priority, Role, SlaEventType, SlaStatus,
)


@dataclass(frozen=True)
class RegisterRequest:
    username: str
    full_name: str
    email: str
    password: str
    department: str = ""


@dataclass(frozen=True)
class CreateIncidentRequest:
    title: str
    description: str
    category_id: int
    service_id: int
    impact: Level
    urgency: Level
    affected_users: int


@dataclass(frozen=True)
class CreateUserRequest:
    username: str
    full_name: str
    email: str
    password: str
    role: Role
    department: str = ""
    admin_level: AdminLevel | None = None
    skills: tuple[str, ...] = ()
    experience_years: int = 0
    max_workload: int = BusinessRules.MAX_ACTIVE_INCIDENTS


@dataclass(frozen=True)
class ServiceRequest:
    name: str
    description: str
    business_criticality: Level
    sla_policy_id: int | None = None
    active: bool = True


@dataclass(frozen=True)
class CategoryRequest:
    name: str
    description: str
    required_skill: str
    active: bool = True


@dataclass(frozen=True)
class SlaPolicyRequest:
    name: str
    is_default: bool
    # Priority -> (response_minutes, resolution_minutes)
    targets: dict[Priority, tuple[int, int]]


@dataclass(frozen=True)
class IncidentSearchCriteria:
    """Every field is optional; only the ones that are set narrow the search."""
    ticket_number: str | None = None
    status: IncidentStatus | None = None
    priority: Priority | None = None
    category_id: int | None = None
    service_id: int | None = None
    technician_id: int | None = None
    reporter_id: int | None = None
    sla_status: SlaStatus | None = None
    from_date: date | None = None      # inclusive, compared with created_at
    to_date: date | None = None        # inclusive of the whole day
    keyword: str | None = None         # matches title or description


@dataclass(frozen=True)
class AuditFilter:
    incident_id: int | None = None
    actor_id: int | None = None
    action: str | None = None
    from_date: date | None = None
    to_date: date | None = None


@dataclass(frozen=True)
class OverviewReport:
    total: int
    open: int
    critical_open: int
    resolved: int
    sla_violations: int


@dataclass(frozen=True)
class WorkloadRow:
    technician_id: int
    technician_name: str
    active_count: int
    max_workload: int


@dataclass(frozen=True)
class CountRow:
    label: str
    count: int


@dataclass(frozen=True)
class SlaViolationRow:
    ticket_number: str
    title: str
    priority: Priority | None
    technician_name: str | None
    event_type: SlaEventType
    recorded_at: datetime
