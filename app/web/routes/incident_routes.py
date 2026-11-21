"""Pages every signed-in user can open: an incident's detail page and the search page.
The service decides who may see what (employees their own incidents, technicians theirs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.domain.enums import IncidentStatus, Priority, Role, SlaStatus
from app.domain.models.user import User
from app.ports.dto import IncidentSearchCriteria
from app.web.actions import ASSIGN, allowed_actions, progress_steps
from app.web.forms import to_date, to_enum, to_int
from app.web.security import get_container, get_current_user
from app.web.template_helpers import flash
from app.web.templating import render

router = APIRouter(prefix="/incidents", dependencies=[Depends(get_current_user)])


_enum, _number, _day = to_enum, to_int, to_date


@router.get("/search")                  # declared before /{incident_id} so "search" is never read as an id
def search_page(request: Request, ticket_number: str = "", status: str = "", priority: str = "",
                category_id: str = "", service_id: str = "", technician_id: str = "", sla_status: str = "",
                from_date: str = "", to_date: str = "", keyword: str = "", user: User = Depends(get_current_user)):
    container = get_container(request)
    form = {"ticket_number": ticket_number.strip(), "status": status, "priority": priority,
            "category_id": category_id, "service_id": service_id, "technician_id": technician_id,
            "sla_status": sla_status, "from_date": from_date, "to_date": to_date, "keyword": keyword.strip()}
    searched = any(form.values())
    results = []
    if searched:
        for name, raw in (("from_date", from_date), ("to_date", to_date)):
            if raw and _day(raw) is None:
                flash(request, f"'{raw}' is not a valid date (use YYYY-MM-DD), so that filter was ignored.", "warning")
        criteria = IncidentSearchCriteria(
            ticket_number=form["ticket_number"] or None, status=_enum(IncidentStatus, status),
            priority=_enum(Priority, priority), category_id=_number(category_id), service_id=_number(service_id),
            technician_id=_number(technician_id), sla_status=_enum(SlaStatus, sla_status),
            from_date=_day(from_date), to_date=_day(to_date), keyword=form["keyword"] or None)
        results = container.incidents.search(user, criteria)
    is_admin = user.role is Role.ADMINISTRATOR
    return render(request, "incident/search.html", {
        "form": form, "searched": searched, "results": results, "is_admin": is_admin,
        "services": container.lookup.list_active_services(user),
        "categories": container.lookup.list_active_categories(user),
        "technicians": container.lookup.list_technicians(user) if is_admin else [],
        "statuses": list(IncidentStatus), "priorities": list(Priority), "sla_statuses": list(SlaStatus)})


@router.get("/{incident_id:int}")
def detail(request: Request, incident_id: int, user: User = Depends(get_current_user)):
    container = get_container(request)
    incident = container.incidents.get_incident(user, incident_id)          # 403 / 404 come from the service
    actions = allowed_actions(user, incident)
    return render(request, "incident/detail.html", {
        "incident": incident, "actions": actions, "steps": progress_steps(incident),
        "trail": container.incidents.get_audit_trail(user, incident_id),
        "technicians": container.lookup.list_technicians(user) if ASSIGN in actions else [],
        "priorities": list(Priority), "is_reporter": incident.reporter.id == user.id,
        "pending_question": next((n for n in reversed(incident.notes) if n.note_type.name == "INFO_REQUEST"), None)
        if incident.has_pending_info_request else None})
