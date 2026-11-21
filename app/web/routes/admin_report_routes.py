"""Administrator pages for reports, the audit log, SLA violations and the demo controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.domain.enums import IncidentEventType, Role
from app.domain.models.user import User
from app.ports.dto import AuditFilter
from app.web.forms import to_date as to_date_parse, to_int
from app.web.security import get_container, require_roles
from app.web.template_helpers import flash
from app.web.templating import render

guard = require_roles(Role.ADMINISTRATOR)
router = APIRouter(prefix="/admin", dependencies=[Depends(guard)])


@router.get("/reports")
def reports(request: Request, user: User = Depends(guard)):
    r = get_container(request).reports
    return render(request, "admin/reports.html", {
        "overview": r.overview(user), "workload": r.technician_workload(user),
        "services": r.service_analysis(user), "categories": r.category_analysis(user),
        "groups": r.correlation_groups(user)})


@router.get("/audit")
def audit(request: Request, incident_id: str = "", actor_id: str = "", action: str = "", from_date: str = "",
          to_date: str = "", user: User = Depends(guard)):
    container = get_container(request)
    form = {"incident_id": incident_id, "actor_id": actor_id, "action": action, "from_date": from_date,
            "to_date": to_date}
    for raw in (from_date, to_date):
        if raw and to_date_parse(raw) is None:
            flash(request, f"'{raw}' is not a valid date (use YYYY-MM-DD), so that filter was ignored.", "warning")
    records = container.reports.audit_log(user, AuditFilter(
        incident_id=to_int(incident_id), actor_id=to_int(actor_id), action=action.strip() or None,
        from_date=to_date_parse(from_date), to_date=to_date_parse(to_date)))
    return render(request, "admin/audit.html", {
        "records": records, "form": form, "actions": [e.name for e in IncidentEventType],
        "people": container.admin.list_users(user)})


@router.get("/sla-violations")
def sla_violations(request: Request, user: User = Depends(guard)):
    return render(request, "admin/sla_violations.html", {
        "rows": get_container(request).reports.sla_violations(user)})


# ---- demo controls ---------------------------------------------------------------------------------------

@router.get("/demo")
def demo(request: Request, user: User = Depends(guard)):
    admin = get_container(request).admin
    simulated = admin.is_time_simulated(user)
    return render(request, "admin/demo.html", {
        "simulated": simulated, "now": admin.get_current_time(user), "choices": [5, 15, 30, 60]})


def _demo_done(request: Request, message: str):
    flash(request, message, "success")
    return RedirectResponse("/admin/demo", status_code=303)


@router.post("/demo/advance")
def advance(request: Request, minutes: str = Form(""), user: User = Depends(guard)):
    new_time = get_container(request).admin.advance_time(user, to_int(minutes))
    return _demo_done(request, f"The demo clock moved forward {minutes} minutes. It is now {new_time:%d %b %Y %H:%M:%S}.")


@router.post("/demo/reset")
def reset(request: Request, user: User = Depends(guard)):
    new_time = get_container(request).admin.reset_time(user)
    return _demo_done(request, f"The demo clock was reset to the real time ({new_time:%d %b %Y %H:%M:%S}).")


@router.post("/demo/run-sla")
def run_sla(request: Request, user: User = Depends(guard)):
    count = get_container(request).admin.run_sla_check_now(user)
    return _demo_done(request, f"SLA check finished: {count} new warning or violation event{'' if count == 1 else 's'} recorded.")


@router.post("/demo/run-escalation")
def run_escalation(request: Request, user: User = Depends(guard)):
    count = get_container(request).admin.run_escalation_check_now(user)
    return _demo_done(request, f"Escalation check finished: {count} incident{'' if count == 1 else 's'} escalated.")
