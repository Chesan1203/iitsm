from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.web import template_helpers as h
from app.web.security import get_container, session_user

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))        # HTML autoescaping is on
templates.env.filters["dt"] = h.format_datetime
templates.env.filters["tm"] = h.format_time
templates.env.filters["label"] = h.label
templates.env.filters["duration"] = h.duration
templates.env.globals.update(PRIORITY_CLASSES=h.PRIORITY_CLASSES, SLA_CLASSES=h.SLA_CLASSES,
                             STATUS_CLASSES=h.STATUS_CLASSES)


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    """Render a page with the things every page needs: the logged-in user, the menu for their
    role, the unread notification count, and any flash messages waiting in the session."""
    user = session_user(request)
    page = {
        "user": user,
        "menu": h.menu_for(user.role, request.url.path) if user else [],
        "unread": get_container(request).notifications.unread_count(user) if user else 0,
        "flashes": h.pop_flashes(request),
    }
    page.update(context or {})
    return templates.TemplateResponse(request, template, page, status_code=status_code)
