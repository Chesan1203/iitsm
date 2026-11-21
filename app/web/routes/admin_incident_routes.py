"""Assignment and priority tools for administrators."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request

from app.domain.enums import Priority, Role
from app.domain.exceptions import InvalidInputError
from app.domain.models.user import User
from app.web.routes.employee_incident_routes import _done, _number
from app.web.security import get_container, require_roles
from app.web.templating import render

guard = require_roles(Role.ADMINISTRATOR)
router = APIRouter(prefix="/incidents", dependencies=[Depends(guard)])


@router.post("/{incident_id:int}/assign")
def assign(request: Request, incident_id: int, technician_id: str = Form(""), user: User = Depends(guard)):
    number = _number(technician_id)
    if number is None:
        raise InvalidInputError("Choose a technician", "technician_id")
    incident = get_container(request).incidents.assign(user, incident_id, number)
    return _done(request, incident_id, f"Assigned to {incident.assigned_technician.full_name}.")


@router.post("/{incident_id:int}/auto-assign")
def auto_assign(request: Request, incident_id: int, user: User = Depends(guard)):
    incident = get_container(request).incidents.auto_assign(user, incident_id)
    return _done(request, incident_id, f"Assigned to {incident.assigned_technician.full_name} by the active strategy.")


@router.get("/{incident_id:int}/recommend")
def recommend(request: Request, incident_id: int, user: User = Depends(guard)):
    container = get_container(request)
    incident = container.incidents.get_incident(user, incident_id)
    return render(request, "incident/recommend.html", {
        "incident": incident, "ranked": container.incidents.recommend_technicians(user, incident_id)})


@router.post("/{incident_id:int}/priority")
def override_priority(request: Request, incident_id: int, priority: str = Form(""), reason: str = Form(""),
                      user: User = Depends(guard)):
    chosen = Priority.__members__.get(priority)
    incident = get_container(request).incidents.override_priority(user, incident_id, chosen, reason)
    return _done(request, incident_id, f"Priority changed to {incident.priority.name}; the SLA deadlines were recalculated.")
