"""One place that turns exceptions into what the user sees (see docs/exceptions.md).

Routes stay thin: they call a service and let errors bubble up to here, except for form pages,
which catch InvalidInputError themselves so they can show the message next to the field.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import (
    ITSMError, NotFoundError, PersistenceError, UnauthorizedOperationError,
)
from app.web.security import NotAuthenticated, safe_next
from app.web.template_helpers import flash
from app.web.templating import render

logger = logging.getLogger(__name__)


_INCIDENT_PATH = re.compile(r"^/incidents/(\d+)(?:/|$)")


def back_url(request: Request, default: str = "/") -> str:
    """Where to send the user after a refused action: the page they came from, if it is on this
    site; otherwise, for an action on an incident, that incident's page; otherwise the default."""
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.netloc == request.url.netloc:
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            if safe_next(target):
                return target
    match = _INCIDENT_PATH.match(request.url.path)
    return f"/incidents/{match.group(1)}" if match else default


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotAuthenticated)
    async def not_authenticated(request: Request, exc: NotAuthenticated):
        target = request.url.path if request.method == "GET" and safe_next(request.url.path) else None
        return RedirectResponse("/login" + (f"?next={target}" if target and target != "/" else ""), status_code=303)

    @app.exception_handler(UnauthorizedOperationError)
    async def forbidden(request: Request, exc: UnauthorizedOperationError):
        return render(request, "errors/403.html", {"message": exc.message}, status_code=403)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return render(request, "errors/404.html", {"message": exc.message}, status_code=404)

    @app.exception_handler(PersistenceError)
    async def persistence_failure(request: Request, exc: PersistenceError):
        logger.error("Database error on %s %s: %s", request.method, request.url.path, exc.message)
        return render(request, "errors/500.html", status_code=500)

    @app.exception_handler(ITSMError)
    async def business_error(request: Request, exc: ITSMError):
        """InvalidStateTransition, TechnicianUnavailable, WorkloadExceeded, MissingSlaConfiguration,
        and any InvalidInput or DuplicateIncident a route did not handle itself: show the message
        once and send the user back."""
        flash(request, exc.message, "danger")
        return RedirectResponse(back_url(request), status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return render(request, "errors/404.html", {"message": "That page does not exist."}, status_code=404)
        return render(request, "errors/400.html", {"message": "That request is not allowed here."},
                      status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return render(request, "errors/400.html", {"message": "That request could not be understood."},
                      status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.error("Unexpected error on %s %s", request.method, request.url.path, exc_info=exc)
        return render(request, "errors/500.html", status_code=500)
