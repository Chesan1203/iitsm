from __future__ import annotations

from app.ports.services import (
    AdminService, AuthService, IncidentService, LookupService, NotificationService, ReportService,
)


class Container:
    """Holds the six services the web layer uses. Built once, at startup.

    Every attribute may be None in the skeleton (placeholder wiring returns an empty one).
    """

    def __init__(self, auth: AuthService | None = None,
                 incidents: IncidentService | None = None,
                 lookup: LookupService | None = None,
                 admin: AdminService | None = None,
                 reports: ReportService | None = None,
                 notifications: NotificationService | None = None):
        self.auth = auth
        self.incidents = incidents
        self.lookup = lookup
        self.admin = admin
        self.reports = reports
        self.notifications = notifications
