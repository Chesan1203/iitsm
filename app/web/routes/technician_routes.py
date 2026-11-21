from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from app.domain.enums import IncidentStatus, Role
from app.domain.models.user import User
from app.ports.dto import IncidentSearchCriteria
from app.web.security import get_container, require_roles
from app.web.templating import render

guard = require_roles(Role.TECHNICIAN)
router = APIRouter(prefix="/tech", dependencies=[Depends(guard)])

_ACTIVE = {IncidentStatus.ASSIGNED, IncidentStatus.ACKNOWLEDGED, IncidentStatus.IN_PROGRESS}


def _urgency_key(incident):
    """Most important first: priority, then the nearest SLA deadline (display ordering only)."""
    tracker = incident.sla_tracker
    return (incident.priority.value if incident.priority else 9,
            tracker.resolution_deadline if tracker else datetime.max)


@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(guard)):
    """My workload and my assigned incidents. The service already limits the search to the
    incidents assigned to this technician."""
    mine = get_container(request).incidents.search(user, IncidentSearchCriteria())
    active = sorted((i for i in mine if i.status in _ACTIVE), key=_urgency_key)
    finished = [i for i in mine if i.status not in _ACTIVE][:10]
    maximum = getattr(user, "max_workload", 0) or 1
    return render(request, "technician/dashboard.html", {
        "active": active, "finished": finished, "workload": len(active), "maximum": maximum,
        "percent": min(100, round(100 * len(active) / maximum))})
