from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.domain.enums import Role
from app.domain.models.user import User
from app.web.security import get_container, require_roles
from app.web.templating import render

guard = require_roles(Role.ADMINISTRATOR)
router = APIRouter(prefix="/admin", dependencies=[Depends(guard)])


@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(guard)):
    reports = get_container(request).reports
    return render(request, "admin/dashboard.html", {
        "overview": reports.overview(user),
        "workload": reports.technician_workload(user),
        "services": reports.service_analysis(user)})
