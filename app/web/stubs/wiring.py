"""Composition root for stub mode: the same six services, backed by in-memory sample data.

Start it with:  ITSM_MODE=stub uvicorn app.main:app --reload
Every user has the password Password@123 (emp1..emp3, tech1..tech3, admin1..admin3). Nothing is
saved, no background jobs run, and restarting the app resets the data.
"""
from app.ports.container import Container
from app.web.stubs.sample_data import build_world
from app.web.stubs.stub_services import (
    StubAdminService, StubAuthService, StubIncidentService, StubLookupService,
    StubNotificationService, StubReportService,
)


def build_stub_container() -> Container:
    world = build_world()
    return Container(
        auth=StubAuthService(world), incidents=StubIncidentService(world),
        lookup=StubLookupService(world), admin=StubAdminService(world),
        reports=StubReportService(world), notifications=StubNotificationService(world))
