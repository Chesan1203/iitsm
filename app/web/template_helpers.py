"""Small helpers for the templates: date formatting, badge colours, the role-aware menu, and
flash messages (a message stored in the session and shown once on the next page)."""
from __future__ import annotations

from datetime import datetime

from fastapi import Request

from app.domain.enums import IncidentStatus, Priority, Role, SlaStatus

PRIORITY_CLASSES = {Priority.P1: "bg-danger", Priority.P2: "bg-orange",
                    Priority.P3: "bg-warning text-dark", Priority.P4: "bg-secondary"}
SLA_CLASSES = {SlaStatus.ON_TRACK: "bg-success", SlaStatus.WARNING: "bg-warning text-dark",
               SlaStatus.VIOLATED: "bg-danger", SlaStatus.MET: "bg-primary"}
STATUS_CLASSES = {IncidentStatus.NEW: "bg-secondary", IncidentStatus.CLASSIFIED: "bg-info text-dark",
                  IncidentStatus.ASSIGNED: "bg-primary", IncidentStatus.ACKNOWLEDGED: "bg-primary",
                  IncidentStatus.IN_PROGRESS: "bg-warning text-dark",
                  IncidentStatus.RESOLVED: "bg-success", IncidentStatus.VERIFIED: "bg-success",
                  IncidentStatus.CLOSED: "bg-dark"}

# (label, url). The first entry whose url prefixes the current path is highlighted.
MENUS: dict[Role, list[tuple[str, str]]] = {
    Role.EMPLOYEE: [("My incidents", "/employee/dashboard"), ("Report incident", "/incidents/new"),
                    ("Search", "/incidents/search"), ("Notifications", "/notifications")],
    Role.TECHNICIAN: [("My work", "/tech/dashboard"), ("Search", "/incidents/search"),
                      ("Notifications", "/notifications")],
    Role.ADMINISTRATOR: [("Dashboard", "/admin/dashboard"), ("All incidents", "/incidents/search"),
                         ("Users", "/admin/users"), ("Services", "/admin/services"),
                         ("Categories", "/admin/categories"), ("SLA policies", "/admin/sla-policies"),
                         ("Strategies", "/admin/strategies"), ("Reports", "/admin/reports"),
                         ("Audit log", "/admin/audit"), ("SLA violations", "/admin/sla-violations"),
                         ("Demo controls", "/admin/demo"), ("Notifications", "/notifications")],
}


def format_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d %b %Y %H:%M")


def format_time(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%H:%M")


def duration(minutes: int | None) -> str:
    """5 becomes '5 min', 120 becomes '2 h', 90 becomes '1 h 30 min'."""
    if minutes is None:
        return "-"
    hours, rest = divmod(int(minutes), 60)
    if hours == 0:
        return f"{rest} min"
    return f"{hours} h" if rest == 0 else f"{hours} h {rest} min"


def label(value) -> str:
    """IN_PROGRESS (an enum member or its name) becomes 'In progress'."""
    if value is None:
        return "-"
    return str(getattr(value, "name", value)).replace("_", " ").capitalize()


def menu_for(role: Role, path: str) -> list[dict]:
    return [{"label": text, "url": url, "active": path == url or (url != "/" and path.startswith(url + "/"))}
            for text, url in MENUS[role]]


# ---- flash messages -----------------------------------------------------------------------------

def flash(request: Request, message: str, category: str = "info") -> None:
    """category: success, info, warning or danger (Bootstrap alert colours).

    The list is reassigned, not appended to in place: the session cookie is only re-sent when
    the session is marked as modified, and changing a list that is already inside it does not."""
    request.session["_flashes"] = [*request.session.get("_flashes", []),
                                   {"category": category, "message": message}]


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])
