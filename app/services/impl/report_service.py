from __future__ import annotations

from app.domain.enums import Role
from app.domain.intelligence.correlation_detector import CorrelationDetector, CorrelationGroup
from app.domain.models.audit import AuditRecord
from app.domain.models.user import User
from app.domain.time_provider import TimeProvider
from app.ports.dto import AuditFilter, CountRow, OverviewReport, SlaViolationRow, WorkloadRow
from app.ports.repositories import AuditRepository, IncidentRepository, ReportRepository
from app.ports.services import ReportService
from app.services.security.access_policy import AccessPolicy


class ReportServiceImpl(ReportService):
    """Administrators only. Mostly passes straight through to the report queries."""

    def __init__(self, reports: ReportRepository, audits: AuditRepository,
                 incidents: IncidentRepository, correlation: CorrelationDetector,
                 time_provider: TimeProvider, access: AccessPolicy):
        self._reports, self._audits, self._incidents = reports, audits, incidents
        self._correlation, self._time, self._access = correlation, time_provider, access

    def _admin(self, actor) -> None:
        self._access.require_role(actor, Role.ADMINISTRATOR)

    def overview(self, actor: User) -> OverviewReport:
        self._admin(actor)
        return self._reports.get_overview()

    def technician_workload(self, actor: User) -> list[WorkloadRow]:
        self._admin(actor)
        return self._reports.get_technician_workload()

    def service_analysis(self, actor: User) -> list[CountRow]:
        self._admin(actor)
        return self._reports.get_service_analysis()

    def category_analysis(self, actor: User) -> list[CountRow]:
        self._admin(actor)
        return self._reports.get_category_analysis()

    def sla_violations(self, actor: User) -> list[SlaViolationRow]:
        self._admin(actor)
        return self._reports.get_sla_violations()

    def audit_log(self, actor: User, audit_filter: AuditFilter) -> list[AuditRecord]:
        self._admin(actor)
        return self._audits.search(audit_filter)

    def correlation_groups(self, actor: User) -> list[CorrelationGroup]:
        """Open incidents grouped by service in the last hour (3 or more = probable service problem)."""
        self._admin(actor)
        return self._correlation.find_groups(self._incidents.find_open(), self._time.now())
