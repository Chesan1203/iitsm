"""Connects the web layer to the application. app/main.py calls install_web(app) once."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.errors import install_error_handlers
from app.web.routes import (
    admin_incident_routes, admin_manage_routes, admin_report_routes, admin_routes, auth_routes,
    common_routes, employee_incident_routes, employee_routes, incident_routes,
    technician_incident_routes, technician_routes,
)


def install_web(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    for module in (auth_routes, common_routes, employee_routes, technician_routes, admin_routes,
                   incident_routes, employee_incident_routes, technician_incident_routes,
                   admin_incident_routes, admin_manage_routes, admin_report_routes):
        app.include_router(module.router)
    install_error_handlers(app)
