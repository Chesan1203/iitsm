from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.domain.enums import IncidentStatus, Role
from app.domain.models.user import User
from app.ports.dto import IncidentSearchCriteria
from app.web.security import get_container, require_roles
from app.web.templating import render

guard = require_roles(Role.EMPLOYEE)
router = APIRouter(prefix="/employee", dependencies=[Depends(guard)])


@router.get("/dashboard")
def dashboard(request: Request, status: str = "", user: User = Depends(guard)):
    """My incidents, newest first, with an optional status filter."""
    chosen = IncidentStatus.__members__.get(status)              # an unknown value simply means "all"
    incidents = get_container(request).incidents.search(user, IncidentSearchCriteria(status=chosen))
    return render(request, "employee/dashboard.html",
                  {"incidents": incidents, "statuses": list(IncidentStatus), "chosen": chosen})
