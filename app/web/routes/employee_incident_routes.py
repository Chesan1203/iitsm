"""Reporting an incident, and the actions an employee (the reporter) can take on it."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.domain.enums import Level, Role
from app.domain.exceptions import (
    CategoryNotFoundError, DuplicateIncidentError, InvalidInputError, ServiceNotFoundError,
)
from app.domain.models.incident import Incident
from app.domain.models.user import User
from app.ports.dto import CreateIncidentRequest
from app.web.forms import field_errors, to_int
from app.web.security import get_container, require_roles
from app.web.template_helpers import flash
from app.web.templating import render

employee_only = require_roles(Role.EMPLOYEE)
employee_or_admin = require_roles(Role.EMPLOYEE, Role.ADMINISTRATOR)
employee_or_technician = require_roles(Role.EMPLOYEE, Role.TECHNICIAN)

router = APIRouter(prefix="/incidents")
REPORT_FIELDS = {"title", "description", "category_id", "service_id", "impact", "urgency", "affected_users"}

IMPACT_HELP = {Level.LOW: "Low: one person or a minor inconvenience",
               Level.MEDIUM: "Medium: several people, or there is a workaround",
               Level.HIGH: "High: many people, or the service cannot be used"}
URGENCY_HELP = {Level.LOW: "Low: can wait", Level.MEDIUM: "Medium: needs attention today",
                Level.HIGH: "High: needs attention right now"}


def _done(request: Request, incident_id: int, message: str):
    flash(request, message, "success")
    return RedirectResponse(f"/incidents/{incident_id}", status_code=303)


_number = to_int


# ---- reporting ---------------------------------------------------------------------------------------

def _form_page(request: Request, values: dict, errors: dict, status_code: int = 200):
    container, user = get_container(request), request.state.user
    return render(request, "incident/new.html", {
        "values": values, "errors": errors, "levels": list(Level),
        "impact_help": IMPACT_HELP, "urgency_help": URGENCY_HELP,
        "services": container.lookup.list_active_services(user),
        "categories": container.lookup.list_active_categories(user)}, status_code=status_code)


@router.get("/new")
def new_form(request: Request, user: User = Depends(employee_only)):
    return _form_page(request, {"impact": "MEDIUM", "urgency": "MEDIUM", "affected_users": "1"}, {})


@router.post("/new")
def report(request: Request, title: str = Form(""), description: str = Form(""), category_id: str = Form(""),
           service_id: str = Form(""), impact: str = Form(""), urgency: str = Form(""),
           affected_users: str = Form(""), user: User = Depends(employee_only)):
    values = {"title": title, "description": description, "category_id": category_id, "service_id": service_id,
              "impact": impact, "urgency": urgency, "affected_users": affected_users}
    try:
        incident = get_container(request).incidents.create_incident(user, CreateIncidentRequest(
            title=title, description=description, category_id=_number(category_id), service_id=_number(service_id),
            impact=Level.__members__.get(impact), urgency=Level.__members__.get(urgency),
            affected_users=_number(affected_users)))
    except InvalidInputError as exc:
        return _form_page(request, values, field_errors(exc, REPORT_FIELDS), 400)
    except ServiceNotFoundError as exc:
        return _form_page(request, values, {"service_id": exc.message}, 400)
    except CategoryNotFoundError as exc:
        return _form_page(request, values, {"category_id": exc.message}, 400)
    except DuplicateIncidentError as exc:
        return _form_page(request, values, {"form": exc.message}, 409)
    for message, category in _creation_messages(incident):
        flash(request, message, category)
    return RedirectResponse(f"/incidents/{incident.id}", status_code=303)


def _creation_messages(incident: Incident) -> list[tuple[str, str]]:
    """What the reporter is told straight after reporting: priority and why, deadlines, who has it."""
    priority, tracker = incident.priority, incident.sla_tracker
    text = f"{incident.ticket_number} was created."
    if priority is not None:
        service = incident.affected_service
        text += (f" Priority {priority.name} ({priority.label}), score {incident.priority_score}: impact "
                 f"{incident.impact.value} x urgency {incident.urgency.value} x service criticality "
                 f"{service.business_criticality.value}.")
    if tracker is not None:
        text += (f" Response due {tracker.response_deadline:%d %b %H:%M}, "
                 f"resolution due {tracker.resolution_deadline:%d %b %H:%M}.")
    tech = incident.assigned_technician
    text += f" Assigned to {tech.full_name}." if tech else " It is waiting for assignment."
    messages = [(text, "success")]
    if incident.possible_duplicate_of:
        messages.append((f"This may be a duplicate of {incident.possible_duplicate_of}. "
                         "It was still created, and an administrator will review it.", "warning"))
    return messages


# ---- reporter actions ----------------------------------------------------------------------------------

@router.post("/{incident_id:int}/respond")
def respond(request: Request, incident_id: int, answer: str = Form(""), user: User = Depends(employee_only)):
    get_container(request).incidents.respond_to_info_request(user, incident_id, answer)
    return _done(request, incident_id, "Your reply was sent to the technician.")


@router.post("/{incident_id:int}/note")
def add_note(request: Request, incident_id: int, text: str = Form(""), user: User = Depends(employee_or_technician)):
    get_container(request).incidents.add_note(user, incident_id, text)
    return _done(request, incident_id, "Your note was added.")


@router.post("/{incident_id:int}/verify")
def verify(request: Request, incident_id: int, user: User = Depends(employee_or_admin)):
    get_container(request).incidents.verify(user, incident_id)
    return _done(request, incident_id, "The resolution was verified.")


@router.post("/{incident_id:int}/reject")
def reject(request: Request, incident_id: int, reason: str = Form(""), user: User = Depends(employee_only)):
    get_container(request).incidents.reject_resolution(user, incident_id, reason)
    return _done(request, incident_id, "The resolution was rejected and the incident is back in progress.")


@router.post("/{incident_id:int}/close")
def close(request: Request, incident_id: int, user: User = Depends(employee_or_admin)):
    get_container(request).incidents.close(user, incident_id)
    return _done(request, incident_id, "The incident was closed.")


@router.post("/{incident_id:int}/feedback")
def feedback(request: Request, incident_id: int, rating: str = Form(""), comment: str = Form(""),
             user: User = Depends(employee_only)):
    get_container(request).incidents.submit_feedback(user, incident_id, _number(rating), comment)
    return _done(request, incident_id, "Thank you for your feedback.")
