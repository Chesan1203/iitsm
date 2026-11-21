"""Web T6: administrator pages (users, services, categories, SLA policies, strategies, reports,
audit log, SLA violations, demo controls)."""
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.enums import Priority
from app.main import create_app
from app.web.stubs.sample_data import PASSWORD
from app.web.template_helpers import duration

from .conftest import login
from .test_incident_pages import GOOD, new_incident_id, page, report

ADMIN_PAGES = ["/admin/users", "/admin/services", "/admin/categories", "/admin/sla-policies", "/admin/strategies",
               "/admin/reports", "/admin/audit", "/admin/sla-violations", "/admin/demo",
               "/admin/services/1/edit", "/admin/categories/1/edit"]
ADMIN_POSTS = ["/admin/users", "/admin/users/1/deactivate", "/admin/users/1/activate", "/admin/users/3/availability",
               "/admin/services", "/admin/services/1/edit", "/admin/categories", "/admin/categories/1/edit",
               "/admin/sla-policies", "/admin/strategies", "/admin/demo/advance", "/admin/demo/reset",
               "/admin/demo/run-sla", "/admin/demo/run-escalation"]


def flashes(html) -> list[str]:
    return [" ".join(m.split()) for m in re.findall(r'<div class="alert[^>]*>(.*?)<button', html, re.S)]


# ---- access ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ADMIN_PAGES)
def test_every_admin_page_is_for_administrators_only(site, anonymous, url):
    assert anonymous.get(url).headers["location"].startswith("/login")
    for who in ("emp1", "tech1"):
        assert login(site, who).get(url).status_code == 403
    assert login(site, "admin1").get(url).status_code == 200


@pytest.mark.parametrize("url", ADMIN_POSTS)
def test_no_admin_action_can_be_posted_by_anyone_else(site, anonymous, url):
    assert anonymous.post(url).headers["location"].startswith("/login")
    for who in ("emp1", "tech1"):
        assert login(site, who).post(url, data={"username": "x", "name": "x"}).status_code == 403


def test_the_duration_helper():
    assert [duration(m) for m in (5, 30, 60, 90, 120, 1440, None)] == ["5 min", "30 min", "1 h", "1 h 30 min", "2 h", "24 h", "-"]


# ---- users --------------------------------------------------------------------------------------------------------

def test_the_users_page_lists_everyone_with_role_specific_details(site):
    html = login(site, "admin1").get("/admin/users").text
    for name in ("emp1", "emp2", "tech1", "tech2", "admin1", "admin2", "admin3"):
        assert f"<td>{name}</td>" in html
    assert "Database" in html and "4 yrs" in html and "available" in html and "Team lead" in html and "Finance" in html


def test_an_administrator_creates_a_technician_who_can_log_in(site):
    admin = login(site, "admin1")
    response = admin.post("/admin/users", data={
        "username": "new.tech", "full_name": "New Tech", "email": "nt@x.com", "password": PASSWORD,
        "role": "TECHNICIAN", "skills": "Network, Security", "experience_years": "3", "max_workload": "4"})
    assert response.status_code == 303 and response.headers["location"] == "/admin/users"
    html = admin.get("/admin/users").text
    assert "Account new.tech was created." in html and "Network, Security" in html and "max 4" in html
    assert login(site, "new.tech").get("/tech/dashboard").status_code == 200


def test_an_administrator_creates_an_employee_and_another_administrator(site):
    admin = login(site, "admin1")
    base = {"email": "x@x.com", "password": PASSWORD}
    admin.post("/admin/users", data={**base, "username": "new.emp", "full_name": "New Emp", "role": "EMPLOYEE", "department": "Ops"})
    admin.post("/admin/users", data={**base, "username": "new.boss", "full_name": "New Boss", "role": "ADMINISTRATOR", "admin_level": "IT_MANAGER"})
    assert login(site, "new.emp").get("/employee/dashboard").status_code == 200
    assert login(site, "new.boss").get("/admin/dashboard").status_code == 200


@pytest.mark.parametrize("data,field", [
    ({"username": "tech1"}, "username"), ({"username": "ab"}, "username"), ({"password": "short"}, "password"),
    ({"email": "nope"}, "email"), ({"full_name": " "}, "full_name"), ({"role": "WIZARD"}, "role"),
    ({"role": "ADMINISTRATOR", "admin_level": ""}, "admin_level"),
    ({"role": "TECHNICIAN", "experience_years": "lots"}, "experience_years"),
    ({"role": "TECHNICIAN", "max_workload": "0"}, "max_workload")])
def test_bad_user_forms_show_the_error_beside_the_field_and_keep_the_entries(site, data, field):
    form = {"username": "fresh.user", "full_name": "Fresh User", "email": "f@x.com", "password": PASSWORD,
            "role": "EMPLOYEE", "department": "Legal", "skills": "", "experience_years": "0", "max_workload": "5", **data}
    response = login(site, "admin1").post("/admin/users", data=form)
    assert response.status_code == 400
    assert re.search(rf'id="{field}"[^>]*is-invalid|is-invalid[^>]*id="{field}"', response.text), field
    assert 'value="Legal"' in response.text and PASSWORD not in response.text
    assert site.repos.users.find_by_username("fresh.user") is None


def test_deactivating_reactivating_and_availability(site):
    admin = login(site, "admin1")
    emp = site.cast.emp2
    assert f"/admin/users/{emp.id}/deactivate" in admin.get("/admin/users").text
    admin.post(f"/admin/users/{emp.id}/deactivate")
    html = admin.get("/admin/users").text
    assert "was deactivated." in html and f"/admin/users/{emp.id}/activate" in html
    assert login_fails(site, "emp2")
    admin.post(f"/admin/users/{emp.id}/activate")
    assert login(site, "emp2").get("/employee/dashboard").status_code == 200

    tech = site.cast.tech1
    admin.post(f"/admin/users/{tech.id}/availability", data={"available": "no"})
    assert "is now on leave." in admin.get("/admin/users").text and site.repos.users.find_by_id(tech.id).available is False
    admin.post(f"/admin/users/{tech.id}/availability", data={"available": "yes"})
    assert site.repos.users.find_by_id(tech.id).available is True


def login_fails(site, username) -> bool:
    return TestClient(site.app).post("/login", data={"username": username, "password": PASSWORD}).status_code == 401


def test_an_administrator_cannot_deactivate_themselves(site):
    admin = login(site, "admin1")
    assert f"/admin/users/{site.cast.admin1.id}/deactivate" not in admin.get("/admin/users").text      # no button
    admin.post(f"/admin/users/{site.cast.admin1.id}/deactivate")                                       # a forged request
    assert "cannot deactivate your own account" in admin.get("/admin/users").text
    assert site.repos.users.find_by_id(site.cast.admin1.id).active


def test_unknown_users_and_non_technician_availability_are_reported(site):
    admin = login(site, "admin1")
    assert admin.post("/admin/users/999/deactivate").status_code == 404
    admin.post(f"/admin/users/{site.cast.emp1.id}/availability", data={"available": "no"})
    assert "Only technicians have an availability" in admin.get("/admin/users").text


def test_names_on_the_users_page_are_escaped(site):
    admin = login(site, "admin1")
    admin.post("/admin/users", data={"username": "xss.user", "full_name": "<script>alert(1)</script>", "email": "a@b.co",
                                     "password": PASSWORD, "role": "EMPLOYEE"})
    html = admin.get("/admin/users").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)</script>" not in html


# ---- services and categories -----------------------------------------------------------------------------------------

def test_adding_and_editing_a_service(site):
    admin = login(site, "admin1")
    admin.post("/admin/services", data={"name": "VPN", "description": "Remote access", "business_criticality": "MEDIUM",
                                        "sla_policy_id": "", "active": "on"})
    html = admin.get("/admin/services").text
    assert "Service VPN was added." in html and "Default policy" in html and "Remote access" in html
    new_id = site.repos.services.find_all()[-1].id
    edit = admin.get(f"/admin/services/{new_id}/edit").text
    assert 'value="VPN"' in edit and 'value="MEDIUM" selected' in edit and "checked" in edit
    admin.post(f"/admin/services/{new_id}/edit", data={"name": "VPN", "description": "Changed", "business_criticality": "HIGH",
                                                       "sla_policy_id": str(site.repos.policies.find_default().id)})
    saved = site.repos.services.find_by_id(new_id)
    assert (saved.description, saved.business_criticality.name, saved.active) == ("Changed", "HIGH", False)
    assert "Service VPN was updated." in admin.get("/admin/services").text


@pytest.mark.parametrize("data,field", [({"name": "payment"}, "name"), ({"name": " "}, "name"),
                                        ({"business_criticality": "EXTREME"}, "business_criticality"),
                                        ({"sla_policy_id": "999"}, "sla_policy_id")])
def test_bad_service_forms_are_explained_beside_the_field(site, data, field):
    form = {"name": "Email", "description": "x", "business_criticality": "LOW", "sla_policy_id": "", "active": "on", **data}
    admin = login(site, "admin1")
    response = admin.post("/admin/services", data=form)
    assert response.status_code == 400 and re.search(rf'id="{field}"[^>]*is-invalid|is-invalid[^>]*id="{field}"', response.text)


def test_a_service_may_keep_its_own_name_when_edited_but_not_take_anothers(site):
    admin = login(site, "admin1")
    admin.post("/admin/services", data={"name": "Email", "business_criticality": "LOW", "active": "on"})
    email_id = next(s.id for s in site.repos.services.find_all() if s.name == "Email")
    same = admin.post(f"/admin/services/{site.service.id}/edit", data={"name": "payment", "business_criticality": "HIGH", "active": "on"})
    assert same.status_code == 303                                          # re-casing its own name is fine
    clash = admin.post(f"/admin/services/{email_id}/edit", data={"name": "PAYMENT", "business_criticality": "LOW", "active": "on"})
    assert clash.status_code == 400 and "already exists" in clash.text


def test_an_unknown_service_or_category_edit_page_is_a_404(site):
    admin = login(site, "admin1")
    assert admin.get("/admin/services/999/edit").status_code == 404
    assert admin.get("/admin/categories/999/edit").status_code == 404
    assert admin.post("/admin/services/999/edit", data={"name": "X", "business_criticality": "LOW"}).status_code == 404


def test_adding_and_editing_a_category(site):
    admin = login(site, "admin1")
    admin.post("/admin/categories", data={"name": "Network", "description": "Net issues", "required_skill": "Network", "active": "on"})
    assert "Category Network was added." in admin.get("/admin/categories").text
    new_id = site.repos.categories.find_all()[-1].id
    admin.post(f"/admin/categories/{new_id}/edit", data={"name": "Network", "description": "x", "required_skill": "Net"})
    saved = site.repos.categories.find_by_id(new_id)
    assert (saved.required_skill, saved.active) == ("Net", False)
    for bad, field in (({"name": "database"}, "name"), ({"required_skill": " "}, "required_skill")):
        response = admin.post("/admin/categories", data={"name": "Other", "required_skill": "x", **bad})
        assert response.status_code == 400 and f'id="{field}"' in response.text


def test_a_new_category_can_be_chosen_when_reporting(site):
    login(site, "admin1").post("/admin/categories", data={"name": "Storage", "required_skill": "Storage", "active": "on"})
    assert "Storage</option>" in login(site, "emp1").get("/incidents/new").text
    site.repos.categories.save(type(site.category)("Storage", "", "Storage", False, id=2))
    assert "Storage</option>" not in login(site, "emp1").get("/incidents/new").text


# ---- SLA policies ---------------------------------------------------------------------------------------------------------

POLICY = {"name": "Strict", "resp_P1": "2", "res_P1": "10", "resp_P2": "10", "res_P2": "60", "resp_P3": "30",
          "res_P3": "240", "resp_P4": "60", "res_P4": "480"}


def test_the_policy_page_shows_each_policy_with_readable_durations(site):
    html = login(site, "admin1").get("/admin/sla-policies").text
    assert "Default" in html and '<span class="badge bg-primary">Default</span>' in html
    for text in ("5 min", "30 min", "2 h", "8 h", "24 h"):
        assert text in html


def test_saving_a_new_policy_and_making_it_the_default(site):
    admin = login(site, "admin1")
    admin.post("/admin/sla-policies", data=POLICY)
    assert "SLA policy Strict was saved." in admin.get("/admin/sla-policies").text
    assert [p.is_default for p in site.repos.policies.find_all()] == [True, False]
    admin.post("/admin/sla-policies", data={**POLICY, "is_default": "on"})
    html = admin.get("/admin/sla-policies").text
    assert html.count('<span class="badge bg-primary">Default</span>') == 1
    assert site.repos.policies.find_default().name == "Strict"


def test_editing_a_policy_prefills_the_form_and_saving_updates_it(site):
    admin = login(site, "admin1")
    admin.post("/admin/sla-policies", data=POLICY)
    policy = next(p for p in site.repos.policies.find_all() if p.name == "Strict")
    html = admin.get(f"/admin/sla-policies?edit={policy.id}").text
    assert "Edit policy: Strict" in html and 'name="resp_P1" value="2"' in html and 'name="res_P4" value="480"' in html
    admin.post("/admin/sla-policies", data={**POLICY, "resp_P1": "3"})
    assert site.repos.policies.find_by_id(policy.id).target_for(Priority.P1).response_minutes == 3
    assert len(site.repos.policies.find_all()) == 2


@pytest.mark.parametrize("change,message", [
    ({"resp_P3": ""}, "must be whole minutes"), ({"res_P2": "abc"}, "must be whole minutes"),
    ({"resp_P1": "40", "res_P1": "10"}, "response target cannot be longer"),
    ({"resp_P4": "0"}, "at least 1"), ({"name": " "}, "name must not be blank")])
def test_bad_policy_forms_are_explained_and_nothing_changes(site, change, message):
    response = login(site, "admin1").post("/admin/sla-policies", data={**POLICY, **change})
    assert response.status_code == 400 and message in response.text            # a message is always shown
    assert 'name="resp_P2" value="10"' in response.text                          # entries are kept
    assert len(site.repos.policies.find_all()) == 1


def test_the_only_default_policy_cannot_be_unset(site):
    response = login(site, "admin1").post("/admin/sla-policies", data={**POLICY, "name": "Default"})
    assert response.status_code == 400 and "one default policy" in response.text
    assert site.repos.policies.find_default().name == "Default"


# ---- strategies ---------------------------------------------------------------------------------------------------------------

def test_the_strategy_page_shows_the_active_choices(site):
    html = login(site, "admin1").get("/admin/strategies").text
    assert re.search(r'id="a-skill_based" value="skill_based" checked', html)
    assert re.search(r'id="p-weighted_score" value="weighted_score" checked', html)
    assert all(n in html for n in ("a-load_based", "a-weighted_recommendation", "p-rule_based"))


def test_switching_the_priority_strategy_changes_the_next_incident(site):
    admin, emp = login(site, "admin1"), login(site, "emp1")
    data = {**GOOD, "urgency": "LOW", "affected_users": "10"}
    first = new_incident_id(emp.post("/incidents/new", data={**data, "title": "Weighted score one"}))
    assert re.search(r'title="High">P2<', page(emp, first))                                # 3 x 1 x 3 = 9
    admin.post("/admin/strategies", data={"assignment": "skill_based", "priority": "rule_based"})
    assert "apply to the next incident" in admin.get("/admin/strategies").text
    second = new_incident_id(emp.post("/incidents/new", data={**data, "title": "Rule based two", "description": "A different text"}))
    assert re.search(r'title="Critical">P1<', page(emp, second))                           # high impact + criticality: always P1


def test_switching_the_assignment_strategy_changes_the_next_assignment(site):
    admin, emp = login(site, "admin1"), login(site, "emp1")
    for n in range(2):
        emp.post("/incidents/new", data={**GOOD, "title": f"Earlier issue {n}", "description": f"Unrelated text number {n}"})
    skill = new_incident_id(emp.post("/incidents/new", data={**GOOD, "title": "Skill based third", "description": "Another text"}))
    assert "Tech1" in page(emp, skill)                                                     # has the skill, still has room
    admin.post("/admin/strategies", data={"assignment": "load_based", "priority": "weighted_score"})
    load = new_incident_id(emp.post("/incidents/new", data={**GOOD, "title": "Load based fourth", "description": "Yet another text"}))
    assert "Tech2" in page(emp, load)                                                      # fewest active incidents


def test_an_unknown_strategy_is_refused_with_a_message(site):
    admin = login(site, "admin1")
    assert admin.post("/admin/strategies", data={"assignment": "nonsense", "priority": "weighted_score"}).status_code == 303
    assert "Unknown strategy" in admin.get("/admin/strategies").text


# ---- reports, audit log, SLA violations ------------------------------------------------------------------------------------------

def test_the_reports_page_shows_numbers_tables_and_related_incidents(site):
    emp = login(site, "emp1")
    for n in range(3):
        emp.post("/incidents/new", data={**GOOD, "title": f"Checkout failing variant {n}", "description": f"Text {n} qrs{n}"})
    html = login(site, "admin1").get("/admin/reports").text
    assert re.search(r'<td>Tech1</td><td class="text-end">3</td>', html)
    assert re.search(r'<td>Payment</td><td class="text-end">3</td>', html)
    assert re.search(r'<td>Database</td><td class="text-end">3</td>', html)
    assert "Probable service problem (3 incidents)" in html


def test_the_reports_page_says_so_when_nothing_is_related(site):
    assert "No related incidents right now." in login(site, "admin1").get("/admin/reports").text


def test_the_audit_log_filters_by_incident_person_action_and_date(site):
    emp, tech, admin = login(site, "emp1"), login(site, "tech1"), login(site, "admin1")
    first = new_incident_id(report(emp, title="Payment gateway down", description="Cannot pay"))
    second = new_incident_id(report(emp, title="Printer on floor 3", description="Out of paper"))
    tech.post(f"/incidents/{first}/acknowledge")

    def log(**params):
        return admin.get("/admin/audit", params=params).text
    everything = log()
    assert re.search(r'id="audit-count">\d+ records', everything) and "INC-1001" in everything and "INC-1002" in everything
    only_first = log(incident_id=str(first))
    assert "INC-1001" in only_first and "INC-1002" not in only_first
    assert "Acknowledged" in log(action="ACKNOWLEDGED") and "INC-1002" not in log(action="ACKNOWLEDGED")
    assert "Tech1" in log(actor_id=str(site.cast.tech1.id)) and "Asha" not in log(actor_id=str(site.cast.tech1.id))
    assert "System" in log(actor_id="0") and "Classified" in log(actor_id="0")
    assert "INC-1001" in log(from_date="2026-11-14", to_date="2026-11-14") and "No records match." in log(from_date="2026-11-15")
    assert "No records match." in log(incident_id=str(second), action="ACKNOWLEDGED")
    assert second and f'href="/incidents/{first}"' in only_first


def test_the_audit_log_ignores_an_invalid_date_and_says_so(site):
    html = login(site, "admin1").get("/admin/audit", params={"from_date": "31/12/2026"}).text
    assert "not a valid date" in html


def test_the_sla_violations_page_starts_empty_and_lists_missed_deadlines(sim_site):
    emp, admin = login(sim_site, "emp1"), login(sim_site, "admin1")
    assert "No SLA violations have been recorded." in admin.get("/admin/sla-violations").text
    report(emp)
    admin.post("/admin/demo/advance", data={"minutes": "60"})
    admin.post("/admin/demo/run-sla")
    html = admin.get("/admin/sla-violations").text
    assert "INC-1001" in html and "Payment application unavailable" in html and "Tech1" in html
    assert "Response" in html and "Resolution" in html


# ---- demo controls --------------------------------------------------------------------------------------------------------------------

def test_the_demo_page_with_a_real_clock_says_time_cannot_be_moved(site):
    admin = login(site, "admin1")
    html = admin.get("/admin/demo").text
    assert "Off (real clock)" in html and "cannot be moved" in html and "/admin/demo/advance" not in html
    admin.post("/admin/demo/advance", data={"minutes": "30"})
    assert "only available when the app runs with simulated time" in admin.get("/admin/demo").text


def test_the_demo_clock_moves_forward_and_resets(sim_site):
    admin = login(sim_site, "admin1")
    html = admin.get("/admin/demo").text
    assert 'fw-semibold">On</div>' in html
    assert all(f'name="minutes" value="{m}"' in html for m in (5, 15, 30, 60))
    admin.post("/admin/demo/advance", data={"minutes": "30"})
    assert "moved forward 30 minutes" in admin.get("/admin/demo").text
    assert sim_site.clock.offset.total_seconds() == 30 * 60
    admin.post("/admin/demo/reset")
    assert "reset to the real time" in admin.get("/admin/demo").text and sim_site.clock.offset.total_seconds() == 0
    admin.post("/admin/demo/advance", data={"minutes": "abc"})
    assert "whole number of at least 1" in admin.get("/admin/demo").text and sim_site.clock.offset.total_seconds() == 0


def test_the_escalation_demo_runs_from_the_pages(sim_site):
    emp, admin = login(sim_site, "emp1"), login(sim_site, "admin1")
    iid = new_incident_id(report(emp))                                     # P1, assigned, nobody has acknowledged it
    admin.post("/admin/demo/run-escalation")
    assert "0 incidents escalated" in admin.get("/admin/demo").text
    admin.post("/admin/demo/advance", data={"minutes": "6"})               # just past the 5-minute response deadline
    admin.post("/admin/demo/run-escalation")
    assert "1 incident escalated" in admin.get("/admin/demo").text
    assert "Team lead" in page(admin, iid)
    admin.post("/admin/demo/run-escalation")
    assert "0 incidents escalated" in admin.get("/admin/demo").text             # polling again changes nothing
    admin.post("/admin/demo/advance", data={"minutes": "10"})              # one more 10-minute step
    admin.post("/admin/demo/run-escalation")
    assert "1 incident escalated" in admin.get("/admin/demo").text and "System admin" in page(admin, iid)
    assert "escalated" in login(sim_site, "admin1").get("/notifications").text


def test_the_sla_check_demo_reports_what_it_found(sim_site):
    emp, admin = login(sim_site, "emp1"), login(sim_site, "admin1")
    report(emp)
    admin.post("/admin/demo/advance", data={"minutes": "4"})               # 80 percent of the 5-minute response window
    admin.post("/admin/demo/run-sla")
    assert "1 new warning or violation event recorded." in admin.get("/admin/demo").text
    admin.post("/admin/demo/run-sla")
    assert "0 new warning or violation events recorded." in admin.get("/admin/demo").text


# ---- the same pages in stub mode ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def stub_admin(tmp_path):
    app = create_app(Settings(ITSM_MODE="stub", ENABLE_SCHEDULER=False, SEED_DEMO_DATA=False,
                              DATABASE_PATH=str(tmp_path / "u.db"), EMAIL_LOG_PATH=str(tmp_path / "e.log")))
    client = TestClient(app, follow_redirects=False)
    assert client.post("/login", data={"username": "admin1", "password": PASSWORD}).status_code == 303
    return client


@pytest.mark.parametrize("url", [u for u in ADMIN_PAGES if "edit" not in u] + ["/admin/services/1/edit", "/admin/categories/1/edit"])
def test_every_admin_page_renders_in_stub_mode(stub_admin, url):
    assert stub_admin.get(url).status_code == 200


def test_the_admin_forms_work_in_stub_mode(stub_admin):
    stub_admin.post("/admin/users", data={"username": "stub.new", "full_name": "Stub New", "email": "s@x.com",
                                          "password": PASSWORD, "role": "EMPLOYEE"})
    assert "<td>stub.new</td>" in stub_admin.get("/admin/users").text
    stub_admin.post("/admin/strategies", data={"assignment": "load_based", "priority": "rule_based"})
    assert re.search(r'id="a-load_based" value="load_based" checked', stub_admin.get("/admin/strategies").text)
    stub_admin.post("/admin/demo/advance", data={"minutes": "15"})
    assert "moved forward 15 minutes" in stub_admin.get("/admin/demo").text
    assert "Technician workload" in stub_admin.get("/admin/reports").text
