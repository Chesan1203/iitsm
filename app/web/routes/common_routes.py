from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.domain.models.user import User
from app.web.errors import back_url
from app.web.security import get_container, get_current_user, home_for
from app.web.templating import render

router = APIRouter(dependencies=[Depends(get_current_user)])      # every page here needs a login


@router.get("/")
def home(user: User = Depends(get_current_user)):
    return RedirectResponse(home_for(user), status_code=303)


@router.get("/notifications")
def notifications(request: Request, user: User = Depends(get_current_user)):
    items = get_container(request).notifications.list_for_user(user, 100)
    return render(request, "common/notifications.html", {"notifications": items})


@router.post("/notifications/read-all")
def mark_all_read(request: Request, user: User = Depends(get_current_user)):
    get_container(request).notifications.mark_all_read(user)
    return RedirectResponse("/notifications", status_code=303)


@router.post("/notifications/{notification_id}/read")
def mark_read(request: Request, notification_id: int, user: User = Depends(get_current_user)):
    get_container(request).notifications.mark_read(user, notification_id)
    return RedirectResponse(back_url(request, "/notifications"), status_code=303)
