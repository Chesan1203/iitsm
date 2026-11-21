from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.domain.exceptions import InvalidInputError, InvalidLoginError
from app.ports.dto import RegisterRequest
from app.web.forms import field_errors
from app.web.security import SESSION_KEY, get_container, home_for, safe_next, session_user
from app.web.template_helpers import flash
from app.web.templating import render

router = APIRouter()          # public pages: no role guard, by design


@router.get("/login")
def login_page(request: Request, next: str = ""):
    user = session_user(request)
    if user is not None:
        return RedirectResponse(home_for(user), status_code=303)
    return render(request, "auth/login.html", {"next": next, "username": "", "error": None})


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("")):
    try:
        user = get_container(request).auth.login(username, password)
    except InvalidLoginError as exc:                  # always the same generic message
        return render(request, "auth/login.html", {"next": next, "username": username, "error": exc.message},
                      status_code=401)
    request.session.clear()                           # drop anything from before logging in
    request.session[SESSION_KEY] = user.id
    request.state.user = user
    return RedirectResponse(safe_next(next) or home_for(user), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "You have been signed out.", "info")
    return RedirectResponse("/login", status_code=303)


@router.get("/register")
def register_page(request: Request):
    user = session_user(request)
    if user is not None:
        return RedirectResponse(home_for(user), status_code=303)
    return render(request, "auth/register.html", {"values": {}, "errors": {}})


@router.post("/register")
def register(request: Request, username: str = Form(""), full_name: str = Form(""), email: str = Form(""),
             password: str = Form(""), department: str = Form("")):
    values = {"username": username, "full_name": full_name, "email": email, "department": department}
    try:
        get_container(request).auth.register_employee(
            RegisterRequest(username=username, full_name=full_name, email=email,
                            password=password, department=department))
    except InvalidInputError as exc:
        return render(request, "auth/register.html",
                      {"values": values, "errors": field_errors(exc, {"username", "full_name", "email", "password"})}, status_code=400)
    flash(request, "Your account was created. Please sign in.", "success")
    return RedirectResponse("/login", status_code=303)
