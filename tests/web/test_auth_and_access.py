"""Web T2/T3: login, registration, sessions, role guards, menus and the error pages."""
import re

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import Role
from app.web.template_helpers import MENUS

from .conftest import PASSWORD, login

PROTECTED = ["/", "/notifications", "/employee/dashboard", "/tech/dashboard", "/admin/dashboard"]


def menu_links(response) -> list[str]:
    """The links in the top navigation bar only (pages may have other nav-link pills too)."""
    navbar = re.search(r"<nav class=\"navbar.*?</nav>", response.text, re.S).group(0)
    return re.findall(r'class="nav-link[^"]*" href="([^"]+)"', navbar)


# ---- W1: anonymous visitors are sent to the login page ----------------------------------------------

@pytest.mark.parametrize("url", PROTECTED)
def test_w1_anonymous_requests_to_protected_pages_redirect_to_login(anonymous, url):
    response = anonymous.get(url)
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_the_page_asked_for_is_remembered_in_the_redirect(anonymous):
    assert anonymous.get("/notifications").headers["location"] == "/login?next=/notifications"
    assert anonymous.get("/").headers["location"] == "/login"


def test_anonymous_post_requests_are_also_blocked_not_just_get(anonymous):
    for url in ("/notifications/read-all", "/notifications/1/read"):
        response = anonymous.post(url)
        assert response.status_code == 303 and response.headers["location"].startswith("/login")


# ---- W2: a wrong role gets 403, whatever URL is typed -----------------------------------------------------------

@pytest.mark.parametrize("who,url,status", [
    ("emp1", "/admin/dashboard", 403), ("emp1", "/tech/dashboard", 403),
    ("tech1", "/admin/dashboard", 403), ("tech1", "/employee/dashboard", 403),
    ("admin1", "/employee/dashboard", 403), ("admin1", "/tech/dashboard", 403),
    ("emp1", "/employee/dashboard", 200), ("tech1", "/tech/dashboard", 200),
    ("admin1", "/admin/dashboard", 200), ("emp1", "/notifications", 200)])
def test_w2_each_role_reaches_only_its_own_pages(site, who, url, status):
    response = login(site, who).get(url)
    assert response.status_code == status
    if status == 403:
        assert "do not have permission" in response.text


# ---- login ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("who,destination", [("emp1", "/employee/dashboard"), ("tech1", "/tech/dashboard"),
                                             ("admin1", "/admin/dashboard")])
def test_login_sends_each_role_to_its_own_dashboard(site, who, destination):
    client = TestClient(site.app, follow_redirects=False)
    response = client.post("/login", data={"username": who, "password": PASSWORD})
    assert response.status_code == 303 and response.headers["location"] == destination
    assert client.get("/").headers["location"] == destination


def test_w6_a_wrong_password_shows_the_generic_message_and_stays_on_the_login_page(site, anonymous):
    for username in ("emp1", "nobody"):                                   # a real user and an unknown one
        response = anonymous.post("/login", data={"username": username, "password": "wrong-password"})
        assert response.status_code == 401
        assert "Invalid username or password" in response.text
        assert 'id="login-error"' in response.text and "<h1 class=\"h4 mb-3\">Sign in</h1>" in response.text
        assert "wrong-password" not in response.text                        # the password is never echoed
        assert "session" not in response.cookies                            # nobody is logged in
    assert 'value="emp1"' in anonymous.post("/login", data={"username": "emp1", "password": "x"}).text
    assert anonymous.get("/employee/dashboard").status_code == 303


def test_a_deactivated_account_cannot_log_in_and_an_existing_session_ends(site):
    client = login(site, "emp1")
    assert client.get("/employee/dashboard").status_code == 200
    site.container.admin.deactivate_user(site.cast.admin1, site.cast.emp1.id)
    response = client.get("/employee/dashboard")                            # next request after deactivation
    assert response.status_code == 303 and response.headers["location"].startswith("/login")
    assert TestClient(site.app).post("/login", data={"username": "emp1", "password": PASSWORD}).status_code == 401


def test_a_session_ended_by_deactivation_does_not_come_back_when_the_account_is_reactivated(site):
    client = login(site, "emp1")
    site.container.admin.deactivate_user(site.cast.admin1, site.cast.emp1.id)
    assert client.get("/employee/dashboard").status_code == 303              # the session is cleared here
    site.container.admin.activate_user(site.cast.admin1, site.cast.emp1.id)
    assert client.get("/employee/dashboard").status_code == 303              # the old cookie no longer works
    assert login(site, "emp1").get("/employee/dashboard").status_code == 200   # a fresh login does


@pytest.mark.parametrize("target,expected", [
    ("/notifications", "/notifications"), ("//evil.example", "/employee/dashboard"),
    ("https://evil.example", "/employee/dashboard"), ("/\\evil.example", "/employee/dashboard"),
    ("", "/employee/dashboard")])
def test_only_a_plain_path_on_this_site_is_used_after_login(site, anonymous, target, expected):
    response = anonymous.post("/login", data={"username": "emp1", "password": PASSWORD, "next": target})
    assert response.headers["location"] == expected


def test_logging_in_replaces_whatever_was_in_the_session(site, anonymous):
    anonymous.post("/notifications/read-all")                                # touches nothing but may set a session
    client = login(site, "emp1")
    assert client.get("/employee/dashboard").status_code == 200
    again = client.post("/login", data={"username": "tech1", "password": PASSWORD})      # switch user in the same browser
    assert again.status_code == 303
    assert client.get("/employee/dashboard").status_code == 403           # now a technician, not an employee


def test_a_logged_in_visitor_to_the_login_page_goes_straight_to_their_home(site):
    assert login(site, "admin1").get("/login").headers["location"] == "/admin/dashboard"


def test_logout_ends_the_session_and_must_be_a_post(site):
    client = login(site, "emp1")
    assert client.get("/logout").status_code == 405                         # a link cannot sign you out
    response = client.post("/logout")
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert "signed out" in client.get("/login").text
    assert client.get("/employee/dashboard").status_code == 303


def test_the_session_cookie_is_http_only_and_same_site_lax(site, anonymous):
    cookie = anonymous.post("/login", data={"username": "emp1", "password": PASSWORD}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


# ---- registration -----------------------------------------------------------------------------------------------

def test_registration_creates_an_employee_who_can_then_log_in(site, anonymous):
    response = anonymous.post("/register", data={"username": "new.hire", "full_name": "New Hire",
                                                 "email": "nh@x.com", "password": PASSWORD, "department": "Ops"})
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert "account was created" in anonymous.get("/login").text
    client = login(site, "new.hire")
    assert client.get("/employee/dashboard").status_code == 200
    assert site.repos.users.find_by_username("new.hire").role is Role.EMPLOYEE


@pytest.mark.parametrize("field,data", [
    ("password", {"password": "short"}), ("username", {"username": "x"}),
    ("email", {"email": "not-an-email"}), ("full_name", {"full_name": "   "}),
    ("username", {"username": "emp1"})])
def test_registration_errors_appear_next_to_the_field_and_the_form_is_kept(anonymous, field, data):
    form = {"username": "fresh.user", "full_name": "Fresh User", "email": "f@x.com", "password": PASSWORD,
            "department": "HR", **data}
    response = anonymous.post("/register", data=form)
    assert response.status_code == 400
    assert re.search(rf'id="{field}"[^>]*is-invalid|is-invalid[^>]*id="{field}"', response.text)
    assert 'class="invalid-feedback d-block"' in response.text
    assert 'value="HR"' in response.text                                    # other entries are kept
    assert PASSWORD not in response.text                                    # the password is never sent back


def test_text_typed_into_forms_is_escaped_not_run(anonymous):
    response = anonymous.post("/register", data={"username": "x", "full_name": "<script>alert(1)</script>",
                                                 "email": "a@b.co", "password": PASSWORD})
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text and "<script>alert(1)</script>" not in response.text


# ---- W5: the menu depends on the role ---------------------------------------------------------------------------------

@pytest.mark.parametrize("who,role,url", [("emp1", Role.EMPLOYEE, "/employee/dashboard"),
                                          ("tech1", Role.TECHNICIAN, "/tech/dashboard"),
                                          ("admin1", Role.ADMINISTRATOR, "/admin/dashboard")])
def test_w5_each_role_sees_its_own_menu(site, who, role, url):
    links = menu_links(login(site, who).get(url))
    assert links == [link for _, link in MENUS[role]]


def test_the_three_menus_really_differ(site):
    menus = {who: tuple(menu_links(login(site, who).get(url)))
             for who, url in (("emp1", "/employee/dashboard"), ("tech1", "/tech/dashboard"), ("admin1", "/admin/dashboard"))}
    assert len(set(menus.values())) == 3
    assert "/incidents/new" in menus["emp1"] and "/incidents/new" not in menus["tech1"]
    assert "/admin/users" in menus["admin1"] and "/admin/users" not in menus["emp1"]
    assert "/admin/demo" in menus["admin1"] and "/admin/demo" not in menus["tech1"]


def test_the_menu_highlights_the_current_page(site):
    html = login(site, "admin1").get("/admin/dashboard").text
    assert re.search(r'class="nav-link active" href="/admin/dashboard"', html)
    assert html.count("nav-link active") == 1


def test_signed_out_pages_show_no_menu_and_no_user(anonymous):
    html = anonymous.get("/login").text
    assert "navbar-nav" not in html and "Sign out" not in html


# ---- error pages ------------------------------------------------------------------------------------------------------

def test_an_unknown_url_shows_a_404_page_for_anyone(site, anonymous):
    for client in (anonymous, login(site, "emp1")):
        response = client.get("/no/such/page")
        assert response.status_code == 404 and "We could not find that." in response.text


def test_a_malformed_url_parameter_is_a_clean_400_page(site):
    response = login(site, "emp1").post("/notifications/abc/read")
    assert response.status_code == 400 and "could not be understood" in response.text


def test_an_unexpected_error_shows_a_generic_500_page_without_details(site):
    def explode():
        raise RuntimeError("secret internal detail /var/db/passwords")
    site.app.add_api_route("/boom", explode)
    client = TestClient(site.app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500 and "Something went wrong on our side." in response.text
    assert "secret internal detail" not in response.text and "Traceback" not in response.text


def test_the_stylesheet_is_served(anonymous):
    response = anonymous.get("/static/css/app.css")
    assert response.status_code == 200 and "bg-orange" in response.text
