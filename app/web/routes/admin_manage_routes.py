"""Administrator pages for managing users, services, categories, SLA policies and strategies.
Every route reads a form, calls ONE admin-service method and redirects; forms that can be filled in
wrongly show the service's error next to the field."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.domain.enums import AdminLevel, Level, Priority, Role
from app.domain.exceptions import CategoryNotFoundError, InvalidInputError, ServiceNotFoundError
from app.domain.models.user import User
from app.ports.dto import CategoryRequest, CreateUserRequest, ServiceRequest, SlaPolicyRequest
from app.web.forms import field_errors, to_enum, to_int, to_list
from app.web.security import get_container, require_roles
from app.web.template_helpers import flash
from app.web.templating import render

guard = require_roles(Role.ADMINISTRATOR)
router = APIRouter(prefix="/admin", dependencies=[Depends(guard)])


def _back(request: Request, path: str, message: str):
    flash(request, message, "success")
    return RedirectResponse(path, status_code=303)


USER_FIELDS = {"username", "full_name", "email", "password", "role", "admin_level", "experience_years", "max_workload"}
SERVICE_FIELDS = {"name", "business_criticality", "sla_policy_id"}
CATEGORY_FIELDS = {"name", "required_skill"}
POLICY_FIELDS = {"name", "targets", "is_default"}


# ====================================================================================================
# Users
# ====================================================================================================

def _users_page(request: Request, user: User, values=None, errors=None, status_code=200):
    return render(request, "admin/users.html", {
        "users": get_container(request).admin.list_users(user), "values": values or {"role": "EMPLOYEE"},
        "errors": errors or {}, "roles": list(Role), "levels": list(AdminLevel)}, status_code=status_code)


@router.get("/users")
def users(request: Request, user: User = Depends(guard)):
    return _users_page(request, user)


@router.post("/users")
def create_user(request: Request, username: str = Form(""), full_name: str = Form(""), email: str = Form(""),
                password: str = Form(""), role: str = Form(""), department: str = Form(""),
                admin_level: str = Form(""), skills: str = Form(""), experience_years: str = Form("0"),
                max_workload: str = Form("5"), user: User = Depends(guard)):
    values = {"username": username, "full_name": full_name, "email": email, "role": role, "department": department,
              "admin_level": admin_level, "skills": skills, "experience_years": experience_years,
              "max_workload": max_workload}
    chosen = to_enum(Role, role)
    try:
        created = get_container(request).admin.create_user(user, CreateUserRequest(
            username=username, full_name=full_name, email=email, password=password, role=chosen,
            department=department, admin_level=to_enum(AdminLevel, admin_level), skills=to_list(skills),
            experience_years=to_int(experience_years), max_workload=to_int(max_workload)))      # only used for technicians
    except InvalidInputError as exc:
        return _users_page(request, user, values, field_errors(exc, USER_FIELDS), 400)
    return _back(request, "/admin/users", f"Account {created.username} was created.")


@router.post("/users/{user_id:int}/deactivate")
def deactivate(request: Request, user_id: int, user: User = Depends(guard)):
    target = get_container(request).admin.deactivate_user(user, user_id)
    return _back(request, "/admin/users", f"{target.full_name} was deactivated.")


@router.post("/users/{user_id:int}/activate")
def activate(request: Request, user_id: int, user: User = Depends(guard)):
    target = get_container(request).admin.activate_user(user, user_id)
    return _back(request, "/admin/users", f"{target.full_name} was reactivated.")


@router.post("/users/{user_id:int}/availability")
def availability(request: Request, user_id: int, available: str = Form(""), user: User = Depends(guard)):
    target = get_container(request).admin.set_technician_availability(user, user_id, available == "yes")
    return _back(request, "/admin/users",
                 f"{target.full_name} is now {'available' if target.available else 'on leave'}.")


# ====================================================================================================
# IT services and categories
# ====================================================================================================

def _service_request(name, description, business_criticality, sla_policy_id, active) -> ServiceRequest:
    return ServiceRequest(name=name, description=description, business_criticality=to_enum(Level, business_criticality),
                          sla_policy_id=to_int(sla_policy_id), active=active == "on")


def _services_page(request, user, template, values=None, errors=None, status_code=200, **extra):
    container = get_container(request)
    return render(request, template, {
        "services": container.admin.list_services(user), "policies": container.admin.list_sla_policies(user),
        "levels": list(Level), "values": values or {"business_criticality": "MEDIUM", "active": "on"},
        "errors": errors or {}, **extra}, status_code=status_code)


@router.get("/services")
def services(request: Request, user: User = Depends(guard)):
    return _services_page(request, user, "admin/services.html")


@router.post("/services")
def create_service(request: Request, name: str = Form(""), description: str = Form(""),
                   business_criticality: str = Form(""), sla_policy_id: str = Form(""), active: str = Form(""),
                   user: User = Depends(guard)):
    values = {"name": name, "description": description, "business_criticality": business_criticality,
              "sla_policy_id": sla_policy_id, "active": active}
    try:
        service = get_container(request).admin.create_service(
            user, _service_request(name, description, business_criticality, sla_policy_id, active))
    except InvalidInputError as exc:
        return _services_page(request, user, "admin/services.html", values, field_errors(exc, SERVICE_FIELDS), 400)
    return _back(request, "/admin/services", f"Service {service.name} was added.")


@router.get("/services/{service_id:int}/edit")
def edit_service_page(request: Request, service_id: int, user: User = Depends(guard)):
    service = next((s for s in get_container(request).admin.list_services(user) if s.id == service_id), None)
    if service is None:
        raise ServiceNotFoundError("The service was not found")
    values = {"name": service.name, "description": service.description,
              "business_criticality": service.business_criticality.name,
              "sla_policy_id": str(service.sla_policy_id or ""), "active": "on" if service.active else ""}
    return _services_page(request, user, "admin/service_edit.html", values, service=service)


@router.post("/services/{service_id:int}/edit")
def edit_service(request: Request, service_id: int, name: str = Form(""), description: str = Form(""),
                 business_criticality: str = Form(""), sla_policy_id: str = Form(""), active: str = Form(""),
                 user: User = Depends(guard)):
    values = {"name": name, "description": description, "business_criticality": business_criticality,
              "sla_policy_id": sla_policy_id, "active": active}
    try:
        service = get_container(request).admin.update_service(
            user, service_id, _service_request(name, description, business_criticality, sla_policy_id, active))
    except InvalidInputError as exc:
        return _services_page(request, user, "admin/service_edit.html", values, field_errors(exc, SERVICE_FIELDS), 400,
                              service=next(s for s in get_container(request).admin.list_services(user) if s.id == service_id))
    return _back(request, "/admin/services", f"Service {service.name} was updated.")


def _categories_page(request, user, template, values=None, errors=None, status_code=200, **extra):
    return render(request, template, {
        "categories": get_container(request).admin.list_categories(user),
        "values": values or {"active": "on"}, "errors": errors or {}, **extra}, status_code=status_code)


@router.get("/categories")
def categories(request: Request, user: User = Depends(guard)):
    return _categories_page(request, user, "admin/categories.html")


@router.post("/categories")
def create_category(request: Request, name: str = Form(""), description: str = Form(""),
                    required_skill: str = Form(""), active: str = Form(""), user: User = Depends(guard)):
    values = {"name": name, "description": description, "required_skill": required_skill, "active": active}
    try:
        category = get_container(request).admin.create_category(
            user, CategoryRequest(name=name, description=description, required_skill=required_skill,
                                  active=active == "on"))
    except InvalidInputError as exc:
        return _categories_page(request, user, "admin/categories.html", values, field_errors(exc, CATEGORY_FIELDS), 400)
    return _back(request, "/admin/categories", f"Category {category.name} was added.")


@router.get("/categories/{category_id:int}/edit")
def edit_category_page(request: Request, category_id: int, user: User = Depends(guard)):
    category = next((c for c in get_container(request).admin.list_categories(user) if c.id == category_id), None)
    if category is None:
        raise CategoryNotFoundError("The category was not found")
    values = {"name": category.name, "description": category.description,
              "required_skill": category.required_skill, "active": "on" if category.active else ""}
    return _categories_page(request, user, "admin/category_edit.html", values, category=category)


@router.post("/categories/{category_id:int}/edit")
def edit_category(request: Request, category_id: int, name: str = Form(""), description: str = Form(""),
                  required_skill: str = Form(""), active: str = Form(""), user: User = Depends(guard)):
    values = {"name": name, "description": description, "required_skill": required_skill, "active": active}
    try:
        category = get_container(request).admin.update_category(
            user, category_id, CategoryRequest(name=name, description=description, required_skill=required_skill,
                                               active=active == "on"))
    except InvalidInputError as exc:
        return _categories_page(request, user, "admin/category_edit.html", values, field_errors(exc, CATEGORY_FIELDS), 400,
                                category=next(c for c in get_container(request).admin.list_categories(user)
                                              if c.id == category_id))
    return _back(request, "/admin/categories", f"Category {category.name} was updated.")


# ====================================================================================================
# SLA policies
# ====================================================================================================

def _policy_values(policy=None) -> dict:
    values = {"name": policy.name if policy else "", "is_default": "on" if policy and policy.is_default else ""}
    for p in Priority:
        target = policy.targets.get(p) if policy else None
        values[f"resp_{p.name}"] = str(target.response_minutes) if target else ""
        values[f"res_{p.name}"] = str(target.resolution_minutes) if target else ""
    return values


def _policies_page(request, user, values=None, errors=None, status_code=200, editing=None):
    return render(request, "admin/sla_policies.html", {
        "policies": get_container(request).admin.list_sla_policies(user), "priorities": list(Priority),
        "values": values if values is not None else _policy_values(editing), "errors": errors or {},
        "editing": editing}, status_code=status_code)


@router.get("/sla-policies")
def sla_policies(request: Request, edit: str = "", user: User = Depends(guard)):
    policies = get_container(request).admin.list_sla_policies(user)
    editing = next((p for p in policies if p.id == to_int(edit)), None)
    return _policies_page(request, user, editing=editing)


@router.post("/sla-policies")
def save_policy(request: Request, name: str = Form(""), is_default: str = Form(""),
                resp_P1: str = Form(""), res_P1: str = Form(""), resp_P2: str = Form(""), res_P2: str = Form(""),
                resp_P3: str = Form(""), res_P3: str = Form(""), resp_P4: str = Form(""), res_P4: str = Form(""),
                user: User = Depends(guard)):
    values = {"name": name, "is_default": is_default, "resp_P1": resp_P1, "res_P1": res_P1, "resp_P2": resp_P2,
              "res_P2": res_P2, "resp_P3": resp_P3, "res_P3": res_P3, "resp_P4": resp_P4, "res_P4": res_P4}
    targets = {p: (to_int(values[f"resp_{p.name}"]), to_int(values[f"res_{p.name}"])) for p in Priority}
    try:
        policy = get_container(request).admin.save_sla_policy(
            user, SlaPolicyRequest(name=name, is_default=is_default == "on", targets=targets))
    except InvalidInputError as exc:
        return _policies_page(request, user, values, field_errors(exc, POLICY_FIELDS), 400)
    return _back(request, "/admin/sla-policies", f"SLA policy {policy.name} was saved.")


# ====================================================================================================
# Strategies
# ====================================================================================================

def _strategies_page(request, user):
    admin = get_container(request).admin
    return render(request, "admin/strategies.html", {
        "assignment_names": admin.list_assignment_strategies(user), "assignment_active": admin.get_assignment_strategy(user),
        "priority_names": admin.list_priority_strategies(user), "priority_active": admin.get_priority_strategy(user)})


@router.get("/strategies")
def strategies(request: Request, user: User = Depends(guard)):
    return _strategies_page(request, user)


@router.post("/strategies")
def set_strategies(request: Request, assignment: str = Form(""), priority: str = Form(""), user: User = Depends(guard)):
    admin = get_container(request).admin
    admin.set_assignment_strategy(user, assignment)
    admin.set_priority_strategy(user, priority)
    return _back(request, "/admin/strategies",
                 f"Assignment strategy: {assignment}. Priority strategy: {priority}. Both apply to the next incident.")
