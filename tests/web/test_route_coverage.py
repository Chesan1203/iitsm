"""Every route in the application must have a deliberate access rule.

The test walks the app's own list of routes (not a hand-copied one). Each route must be either public
or match exactly one rule below, so a NEW route added without a guard, or without a decision about who may
use it, fails here. For each rule it then checks the real behaviour: anonymous visitors are redirected to
the login page, and every role that is not allowed gets a 403 before the route does anything.
"""
import re

import pytest
from fastapi.testclient import TestClient

from .conftest import login

PUBLIC = {"/login", "/register", "/logout", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

EMP, TECH, ADMIN = "emp1", "tech1", "admin1"
ROLES = {"employee": EMP, "technician": TECH, "administrator": ADMIN}

# (pattern, roles allowed through the guard). "any" means any signed-in user.
RULES = [
    (r"^/admin/", {"administrator"}),
    (r"^/tech/", {"technician"}),
    (r"^/employee/", {"employee"}),
    (r"^/incidents/new$", {"employee"}),
    (r"^/incidents/\{incident_id\}/(assign|auto-assign|recommend|priority)$", {"administrator"}),
    (r"^/incidents/\{incident_id\}/(acknowledge|start|request-info|resolve)$", {"technician"}),
    (r"^/incidents/\{incident_id\}/(respond|reject|feedback)$", {"employee"}),
    (r"^/incidents/\{incident_id\}/(verify|close)$", {"employee", "administrator"}),
    (r"^/incidents/\{incident_id\}/note$", {"employee", "technician"}),
    (r"^(/|/notifications|/notifications/read-all|/notifications/\{notification_id\}/read"
     r"|/incidents/search|/incidents/\{incident_id\})$", {"employee", "technician", "administrator"}),
]


def operations(app):
    paths = app.openapi()["paths"]
    return sorted((method.upper(), path) for path, ops in paths.items() for method in ops)


def rule_for(path):
    matches = [roles for pattern, roles in RULES if re.match(pattern, path)]
    assert len(matches) <= 1, f"{path} matches more than one access rule"
    return matches[0] if matches else None


def concrete(path):
    return re.sub(r"\{[^}]+\}", "1", path)


def call(client, method, path):
    return client.request(method, concrete(path), data={} if method == "POST" else None)


def test_every_route_is_public_on_purpose_or_has_an_access_rule(site):
    unclassified = [f"{m} {p}" for m, p in operations(site.app) if p not in PUBLIC and rule_for(p) is None]
    assert not unclassified, ("These routes have no access rule. Add the guard to their router and a rule "
                              f"to RULES in this test: {unclassified}")


def test_the_route_list_is_really_the_whole_application(site):
    ops = operations(site.app)
    found = {p for _, p in ops}
    assert len(ops) >= 55                                    # a sanity check that the walk did not silently shrink
    assert {"/admin/users", "/incidents/{incident_id}/assign", "/tech/dashboard", "/incidents/new"} <= found


def test_anonymous_visitors_are_redirected_to_login_from_every_protected_route(site):
    anonymous = TestClient(site.app, follow_redirects=False)
    failures = []
    for method, path in operations(site.app):
        if path in PUBLIC:
            continue
        response = call(anonymous, method, path)
        if response.status_code != 303 or not response.headers.get("location", "").startswith("/login"):
            failures.append(f"{method} {path} -> {response.status_code}")
    assert not failures, failures


def test_every_role_that_is_not_allowed_gets_403_before_the_route_does_anything(site):
    clients = {role: login(site, username) for role, username in ROLES.items()}
    failures = []
    for method, path in operations(site.app):
        allowed = rule_for(path)
        if path in PUBLIC or allowed is None:
            continue
        for role, client in clients.items():
            if role in allowed:
                continue
            response = call(client, method, path)
            if response.status_code != 403:
                failures.append(f"{role} {method} {path} -> {response.status_code}")
    assert not failures, failures
    assert site.repos.incidents.all_incidents() == []        # nothing was created or changed on the way


@pytest.mark.parametrize("path", sorted(PUBLIC - {"/logout", "/docs/oauth2-redirect"}))
def test_the_public_routes_really_are_reachable_without_signing_in(site, path):
    response = TestClient(site.app, follow_redirects=False).get(path)
    assert response.status_code == 200
