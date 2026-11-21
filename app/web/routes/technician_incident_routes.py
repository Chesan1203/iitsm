"""Actions the assigned technician takes on an incident."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request

from app.domain.enums import Role
from app.domain.models.user import User
from app.web.routes.employee_incident_routes import _done
from app.web.security import get_container, require_roles

guard = require_roles(Role.TECHNICIAN)
router = APIRouter(prefix="/incidents", dependencies=[Depends(guard)])


@router.post("/{incident_id:int}/acknowledge")
def acknowledge(request: Request, incident_id: int, user: User = Depends(guard)):
    get_container(request).incidents.acknowledge(user, incident_id)
    return _done(request, incident_id, "You acknowledged the incident.")


@router.post("/{incident_id:int}/start")
def start(request: Request, incident_id: int, user: User = Depends(guard)):
    get_container(request).incidents.start_investigation(user, incident_id)
    return _done(request, incident_id, "Investigation started.")


@router.post("/{incident_id:int}/request-info")
def request_info(request: Request, incident_id: int, question: str = Form(""), user: User = Depends(guard)):
    get_container(request).incidents.request_info(user, incident_id, question)
    return _done(request, incident_id, "Your question was sent to the reporter.")


@router.post("/{incident_id:int}/resolve")
def resolve(request: Request, incident_id: int, summary: str = Form(""), details: str = Form(""),
            user: User = Depends(guard)):
    get_container(request).incidents.resolve(user, incident_id, summary, details)
    return _done(request, incident_id, "The incident was marked as resolved.")
