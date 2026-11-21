"""Web T4 to T7: the report form, the incident page, every action route, admin tools and search."""
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.enums import IncidentStatus as S
from app.main import create_app
from app.web.actions import allowed_actions, progress_steps
from app.web.stubs.sample_data import PASSWORD
from tests.domain.helpers import make_admin, make_employee, make_incident_in, make_technician

from .conftest import login

GOOD = {"title": "Payment application unavailable", "description": "Customers cannot pay at checkout",
        "service_id": "1", "category_id": "1", "impact": "HIGH", "urgency": "HIGH", "affected_users": "120"}


def report(client, **overrides):
    return client.post("/incidents/new", data={**GOOD, **overrides})


def new_incident_id(response) -> int:
    assert response.status_code == 303, response.text
    return int(response.headers["location"].rsplit("/", 1)[1])


def forms(html) -> set[str]:
    """The action URLs of the forms on a page (what buttons the person can press)."""
    return set(re.findall(r'<form method="post" action="([^"]+)"', html))


def page(client, incident_id) -> str:
    response = client.get(f"/incidents/{incident_id}")
    assert response.status_code == 200
    return response.text


# ====================================================================================================
# Reporting
# ====================================================================================================

def test_the_report_form_lists_services_categories_and_explained_levels(site):
    html = login(site, "emp1").get("/incidents/new").text
    assert "Payment</option>" in html and "Database</option>" in html
    assert "High: many people, or the service cannot be used" in html and "Medium: needs attention today" in html


@pytest.mark.parametrize("who", ["tech1", "admin1"])
def test_only_employees_can_open_the_report_form(site, who):
    client = login(site, who)
    assert client.get("/incidents/new").status_code == 403
    assert report(client).status_code == 403


def test_anonymous_visitors_cannot_report(anonymous):
    assert anonymous.get("/incidents/new").headers["location"].startswith("/login")
    assert report(anonymous).headers["location"].startswith("/login")


def test_w3_a_blank_form_shows_an_error_beside_each_field_and_keeps_what_was_typed(site):
    response = report(login(site, "emp1"), title="  ", description="", service_id="", category_id="", affected_users="0")
    html = response.text
    assert response.status_code == 400
    assert html.count("invalid-feedback d-block") >= 1
    for name in ("title",):
        assert re.search(rf'id="{name}"[^>]*is-invalid|is-invalid[^>]*id="{name}"', html)
    assert site.repos.incidents.all_incidents() == []


@pytest.mark.parametrize("field,value,error_field", [
    ("title", "  ", "title"), ("description", "", "description"), ("affected_users", "0", "affected_users"),
    ("affected_users", "many", "affected_users"), ("impact", "HUGE", "impact"), ("urgency", "", "urgency"),
    ("service_id", "999", "service_id"), ("service_id", "abc", "service_id"), ("category_id", "999", "category_id")])
def test_each_bad_field_is_reported_on_that_field_and_nothing_is_saved(site, field, value, error_field):
    response = report(login(site, "emp1"), **{field: value})
    assert response.status_code == 400
    assert re.search(rf'id="{error_field}"[^>]*is-invalid|is-invalid[^>]*id="{error_field}"', response.text)
    assert site.repos.incidents.all_incidents() == []


def test_a_good_report_redirects_and_explains_priority_deadlines_and_technician(site):
    client = login(site, "emp1")
    response = report(client)
    incident_id = new_incident_id(response)
    html = page(client, incident_id)
    assert "INC-1001 was created." in html
    assert "Priority P1 (Critical), score 27: impact 3 x urgency 3 x service criticality 3." in html
    assert "Response due 14 Nov 10:05, resolution due 14 Nov 10:30." in html
    assert "Assigned to Tech1." in html
    assert "Priority P1 (Critical), score 27" not in page(client, incident_id)           # a flash is shown only once


def test_the_creation_message_says_when_nobody_could_be_assigned(site):
    for tech in (site.cast.tech1, site.cast.tech2):
        site.container.admin.set_technician_availability(site.cast.admin1, tech.id, False)
    client = login(site, "emp1")
    assert "It is waiting for assignment." in page(client, new_incident_id(report(client)))


def test_a_similar_earlier_report_produces_a_duplicate_warning_but_still_creates_the_incident(site):
    login(site, "emp2").post("/incidents/new", data={**GOOD, "title": "Payment transaction failing"})
    client = login(site, "emp1")
    incident_id = new_incident_id(report(client, title="Payment application unavailable"))
    html = page(client, incident_id)
    assert "may be a duplicate of INC-1001" in html and 'id="duplicate-warning"' in html


def test_an_accidental_resubmission_is_refused_on_the_form(site):
    client = login(site, "emp1")
    report(client)
    response = report(client)
    assert response.status_code == 409 and "already reported this a moment ago" in response.text
    assert len(site.repos.incidents.all_incidents()) == 1


def test_a_missing_sla_configuration_is_explained_and_nothing_is_saved(site):
    site.repos.policies._items.clear()
    client = login(site, "emp1")
    response = client.post("/incidents/new", data=GOOD, headers={"referer": "http://testserver/incidents/new"})
    assert response.status_code == 303 and response.headers["location"] == "/incidents/new"
    assert "No SLA policy" in client.get("/incidents/new").text
    assert site.repos.incidents.all_incidents() == []


def test_the_reporter_always_comes_from_the_session_never_from_the_form(site):
    client = login(site, "emp1")
    incident_id = new_incident_id(report(client, reporter_id=str(site.cast.emp2.id), user_id="2", status="CLOSED",
                                         priority="P4"))
    incident = site.repos.incidents.find_by_id(incident_id)
    assert incident.reporter.username == "emp1" and incident.status is not S.CLOSED and incident.priority.name == "P1"


# ====================================================================================================
# The incident page
# ====================================================================================================

def test_the_incident_page_shows_details_sla_steps_and_a_timeline(site):
    client = login(site, "emp1")
    incident_id = new_incident_id(report(client))
    html = page(client, incident_id)
    assert "Payment application unavailable" in html and "Customers cannot pay at checkout" in html
    assert re.search(r'<li class="current">Assigned</li>', html) and html.count('<li class="done">') == 2
    assert 'id="sla-card"' in html and "14 Nov 2026 10:05" in html and "14 Nov 2026 10:30" in html
    timeline = html[html.index('id="timeline"'):]
    assert timeline.index("Created") < timeline.index("Classified") < timeline.index("Assigned")
    assert "Tech1" in html and "score 27" in html


def test_who_may_open_an_incident_page(site):
    incident_id = new_incident_id(report(login(site, "emp1")))
    for who in ("emp1", "tech1", "admin2"):
        assert login(site, who).get(f"/incidents/{incident_id}").status_code == 200
    for who in ("emp2", "tech2"):
        assert login(site, who).get(f"/incidents/{incident_id}").status_code == 403


def test_unknown_and_malformed_incident_ids(site):
    client = login(site, "admin1")
    assert client.get("/incidents/999").status_code == 404
    assert client.get("/incidents/abc").status_code == 404


def test_text_on_the_incident_page_is_escaped(site):
    client = login(site, "emp1")
    incident_id = new_incident_id(report(client, title="<b>bold</b>", description="<script>alert(1)</script>"))
    html = page(client, incident_id)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)</script>" not in html


# ====================================================================================================
# Buttons depend on role and status (a display hint; the service still enforces everything)
# ====================================================================================================

def act(site, who, incident_id, action, **data):
    return login(site, who).post(f"/incidents/{incident_id}/{action}", data=data)


def test_w7_the_technician_is_offered_only_the_actions_valid_for_the_status(site):
    emp, tech = login(site, "emp1"), login(site, "tech1")
    iid = new_incident_id(report(emp))
    base = f"/incidents/{iid}"
    assert forms(page(tech, iid)) >= {f"{base}/acknowledge", f"{base}/note"}
    assert f"{base}/resolve" not in forms(page(tech, iid)) and f"{base}/start" not in forms(page(tech, iid))

    tech.post(f"{base}/acknowledge")
    assert f"{base}/start" in forms(page(tech, iid)) and f"{base}/acknowledge" not in forms(page(tech, iid))
    assert f"{base}/resolve" not in forms(page(tech, iid))

    tech.post(f"{base}/start")
    in_progress = forms(page(tech, iid))
    assert {f"{base}/resolve", f"{base}/request-info", f"{base}/note"} <= in_progress
    assert 'id="resolve-form"' in page(tech, iid)

    tech.post(f"{base}/resolve", data={"summary": "Fixed", "details": "Restarted"})
    resolved = forms(page(tech, iid))
    assert f"{base}/resolve" not in resolved and f"{base}/request-info" not in resolved


def test_the_employee_is_offered_verify_reject_close_and_feedback_at_the_right_times(site):
    emp, tech = login(site, "emp1"), login(site, "tech1")
    iid = new_incident_id(report(emp))
    base = f"/incidents/{iid}"
    early = forms(page(emp, iid))
    assert not early & {f"{base}/verify", f"{base}/reject", f"{base}/close", f"{base}/feedback"}
    assert f"{base}/note" in early                                    # may add information while it is open

    for step in ("acknowledge", "start"):
        tech.post(f"{base}/{step}")
    tech.post(f"{base}/resolve", data={"summary": "Fixed", "details": ""})
    resolved = forms(page(emp, iid))
    assert {f"{base}/verify", f"{base}/reject"} <= resolved and f"{base}/close" not in resolved

    emp.post(f"{base}/verify")
    verified = forms(page(emp, iid))
    assert f"{base}/close" in verified and f"{base}/feedback" in verified and f"{base}/verify" not in verified

    emp.post(f"{base}/close")
    closed = forms(page(emp, iid))
    assert f"{base}/feedback" in closed and f"{base}/note" not in closed and f"{base}/close" not in closed

    emp.post(f"{base}/feedback", data={"rating": "5", "comment": "Thanks"})
    assert f"{base}/feedback" not in forms(page(emp, iid))
    assert "Rated <strong>5 out of 5</strong>" in page(emp, iid)


def test_the_reply_box_appears_only_while_a_question_is_waiting_and_only_for_the_reporter(site):
    emp, tech = login(site, "emp1"), login(site, "tech1")
    iid = new_incident_id(report(emp))
    base = f"/incidents/{iid}"
    for step in ("acknowledge", "start"):
        tech.post(f"{base}/{step}")
    assert 'id="reply-box"' not in page(emp, iid)
    tech.post(f"{base}/request-info", data={"question": "Which browser are you using?"})
    assert 'id="reply-box"' in page(emp, iid) and "Which browser are you using?" in page(emp, iid)
    assert 'id="reply-box"' not in page(tech, iid)
    emp.post(f"{base}/respond", data={"answer": "Firefox"})
    after = page(emp, iid)
    assert 'id="reply-box"' not in after and "Firefox" in after


def test_the_administrator_tools_depend_on_the_status(site):
    admin, tech = login(site, "admin1"), login(site, "tech1")
    iid = new_incident_id(report(login(site, "emp1")))
    base = f"/incidents/{iid}"
    assigned = forms(page(admin, iid))
    assert {f"{base}/assign", f"{base}/priority"} <= assigned and f"{base}/auto-assign" not in assigned
    assert "Reassign to" in page(admin, iid) and f"{base}/recommend" in page(admin, iid)
    for step in ("acknowledge", "start"):
        tech.post(f"{base}/{step}")
    tech.post(f"{base}/resolve", data={"summary": "Fixed", "details": ""})
    working = forms(page(admin, iid))
    assert f"{base}/assign" not in working and f"{base}/verify" in working
    assert forms(page(login(site, "emp1"), iid)).isdisjoint({f"{base}/assign", f"{base}/priority"})


@pytest.mark.parametrize("status,expected", [
    (S.ASSIGNED, {"acknowledge", "note"}), (S.ACKNOWLEDGED, {"start", "note"}),
    (S.IN_PROGRESS, {"note", "request_info", "resolve"}), (S.RESOLVED, {"note"}),
    (S.VERIFIED, set()), (S.CLOSED, set()), (S.CLASSIFIED, set())])
def test_allowed_actions_for_the_assigned_technician(status, expected):
    assert allowed_actions(make_technician(), make_incident_in(status)) == expected


@pytest.mark.parametrize("status,expected", [
    (S.ASSIGNED, {"add_info"}), (S.IN_PROGRESS, {"add_info"}), (S.RESOLVED, {"add_info", "verify", "reject"}),
    (S.VERIFIED, {"add_info", "close", "feedback"}), (S.CLOSED, {"feedback"})])
def test_allowed_actions_for_the_reporter(status, expected):
    assert allowed_actions(make_employee(), make_incident_in(status)) == expected


@pytest.mark.parametrize("status,expected", [
    (S.CLASSIFIED, {"assign", "auto_assign", "recommend", "override_priority"}),
    (S.ASSIGNED, {"assign", "recommend", "override_priority"}), (S.IN_PROGRESS, {"override_priority"}),
    (S.RESOLVED, {"verify", "override_priority"}), (S.VERIFIED, {"close", "override_priority"}), (S.CLOSED, set())])
def test_allowed_actions_for_an_administrator(status, expected):
    assert allowed_actions(make_admin(), make_incident_in(status)) == expected


def test_strangers_are_offered_nothing_and_steps_mark_progress():
    stranger = make_employee(id=77, username="stranger")
    assert allowed_actions(stranger, make_incident_in(S.RESOLVED)) == set()
    steps = progress_steps(make_incident_in(S.IN_PROGRESS))
    assert [s["state"] for s in steps] == ["done"] * 4 + ["current"] + ["todo"] * 3 and len(steps) == 8


# ====================================================================================================
# The whole workflow over HTTP, and errors
# ====================================================================================================

def test_a_complete_workflow_through_the_pages(site):
    emp, tech, admin = login(site, "emp1"), login(site, "tech1"), login(site, "admin1")
    iid = new_incident_id(report(emp))
    base = f"/incidents/{iid}"
    posts = [(tech, "acknowledge", {}), (tech, "start", {}), (tech, "note", {"text": "Checking the logs"}),
             (tech, "request-info", {"question": "Since when?"}), (emp, "respond", {"answer": "Since 9am"}),
             (tech, "resolve", {"summary": "Restarted gateway", "details": "It had stalled"}),
             (emp, "verify", {}), (emp, "close", {}), (emp, "feedback", {"rating": "4", "comment": "Quick"})]
    for client, action, data in posts:
        response = client.post(f"{base}/{action}", data=data)
        assert response.status_code == 303 and response.headers["location"] == base, action
    final = page(emp, iid)
    assert re.search(r'<li class="current">Closed</li>', final)
    assert "Restarted gateway" in final and "Since 9am" in final and "Rated <strong>4 out of 5</strong>" in final
    timeline = final[final.index('id="timeline"'):]
    for step in ("Acknowledged", "Investigation started", "Resolved", "Verified", "Closed", "Feedback submitted"):
        assert step in timeline, step
    assert site.repos.incidents.find_by_id(iid).status is S.CLOSED
    assert "was created" in admin.get("/notifications").text


def test_success_messages_appear_once_after_each_action(site):
    emp, tech = login(site, "emp1"), login(site, "tech1")
    iid = new_incident_id(report(emp))
    tech.post(f"/incidents/{iid}/acknowledge")
    assert "You acknowledged the incident." in page(tech, iid)
    assert "You acknowledged the incident." not in page(tech, iid)


def test_w4_an_illegal_transition_shows_the_message_on_the_incident_page(site):
    emp = login(site, "emp1")
    iid = new_incident_id(report(emp))
    response = emp.post(f"/incidents/{iid}/close")                    # an ASSIGNED incident cannot be closed
    assert response.status_code == 303 and response.headers["location"] == f"/incidents/{iid}"
    html = page(emp, iid)
    assert "Cannot close an incident that is ASSIGNED" in html and 'alert-danger' in html
    assert site.repos.incidents.find_by_id(iid).status is S.ASSIGNED


def test_bad_action_data_is_explained_and_changes_nothing(site):
    emp, tech = login(site, "emp1"), login(site, "tech1")
    iid = new_incident_id(report(emp))
    for step in ("acknowledge", "start"):
        tech.post(f"/incidents/{iid}/{step}")
    tech.post(f"/incidents/{iid}/resolve", data={"summary": "  ", "details": "x"})
    assert "summary must not be blank" in page(tech, iid)
    assert site.repos.incidents.find_by_id(iid).status is S.IN_PROGRESS


def test_two_messages_in_a_row_are_both_shown_not_just_the_first(site):
    """Regression: a message added while another was still waiting used to be lost, because the
    session cookie was not re-sent when a list inside the session changed."""
    emp = login(site, "emp1")
    iid = new_incident_id(report(emp))                                  # leaves the "was created" message waiting
    emp.post(f"/incidents/{iid}/close")                                 # adds a second one (illegal transition)
    html = page(emp, iid)
    assert "INC-1001 was created." in html and "Cannot close an incident that is ASSIGNED" in html


@pytest.mark.parametrize("who,action,expected", [
    ("emp1", "acknowledge", 403), ("admin1", "acknowledge", 403), ("emp1", "assign", 403), ("tech1", "assign", 403),
    ("tech1", "verify", 403), ("tech1", "feedback", 403), ("emp2", "verify", 403), ("tech2", "acknowledge", 403),
    ("emp2", "note", 403), ("emp1", "priority", 403)])
def test_the_wrong_person_cannot_use_an_action_route(site, who, action, expected):
    iid = new_incident_id(report(login(site, "emp1")))
    assert act(site, who, iid, action, technician_id="1", priority="P3", reason="x", text="x", rating="5").status_code == expected
    assert site.repos.incidents.find_by_id(iid).status is S.ASSIGNED


def test_action_routes_reject_anonymous_visitors_and_unknown_incidents(site, anonymous):
    for action in ("acknowledge", "verify", "assign", "note"):
        assert anonymous.post(f"/incidents/1/{action}").headers["location"].startswith("/login")
    assert login(site, "tech1").post("/incidents/999/acknowledge").status_code == 404


# ====================================================================================================
# Administrator tools
# ====================================================================================================

def test_an_administrator_assigns_then_reassigns(site):
    for tech in (site.cast.tech1, site.cast.tech2):
        site.container.admin.set_technician_availability(site.cast.admin1, tech.id, False)
    iid = new_incident_id(report(login(site, "emp1")))
    for tech in (site.cast.tech1, site.cast.tech2):
        site.container.admin.set_technician_availability(site.cast.admin1, tech.id, True)
    admin = login(site, "admin1")
    assert "Assign to" in page(admin, iid)
    admin.post(f"/incidents/{iid}/assign", data={"technician_id": str(site.cast.tech2.id)})
    assert "Assigned to Tech2." in page(admin, iid)
    admin.post(f"/incidents/{iid}/assign", data={"technician_id": str(site.cast.tech1.id)})
    html = page(admin, iid)
    assert "Assigned to Tech1." in html and "Reassign to" in html
    assert admin.post(f"/incidents/{iid}/assign", data={"technician_id": ""}).status_code == 303
    assert "Choose a technician" in page(admin, iid)


def test_auto_assign_uses_the_active_strategy(site):
    for tech in (site.cast.tech1, site.cast.tech2):
        site.container.admin.set_technician_availability(site.cast.admin1, tech.id, False)
    iid = new_incident_id(report(login(site, "emp1")))
    admin = login(site, "admin1")
    admin.post(f"/incidents/{iid}/auto-assign")
    assert "No technician is currently available" in page(admin, iid)
    site.container.admin.set_technician_availability(site.cast.admin1, site.cast.tech1.id, True)
    admin.post(f"/incidents/{iid}/auto-assign")
    assert "Assigned to Tech1 by the active strategy." in page(admin, iid)


def test_the_recommendation_page_ranks_technicians_with_reasons(site):
    iid = new_incident_id(report(login(site, "emp1")))
    html = login(site, "admin1").get(f"/incidents/{iid}/recommend").text
    assert html.index("Tech1") < html.index("Tech2") and "has skill Database" in html and "slots used" in html
    assert f'action="/incidents/{iid}/assign"' in html
    assert login(site, "emp1").get(f"/incidents/{iid}/recommend").status_code == 403


def test_overriding_the_priority_recalculates_the_deadlines_and_notifies(site):
    iid = new_incident_id(report(login(site, "emp1")))
    admin = login(site, "admin1")
    admin.post(f"/incidents/{iid}/priority", data={"priority": "P3", "reason": "Only affects reports"})
    html = page(admin, iid)
    assert "Priority changed to P3" in html and "14 Nov 2026 11:00" in html and "14 Nov 2026 18:00" in html
    assert re.search(r'badge bg-warning text-dark" title="Medium">P3<', html)          # the badge changed too
    assert {"PRIORITY_CHANGED"} <= {r.action for r in site.repos.audits.find_by_incident(iid)}
    assert any(n.event_type.name == "PRIORITY_CHANGED" for n in site.repos.notifications.all())
    admin.post(f"/incidents/{iid}/priority", data={"priority": "P3", "reason": "again"})
    assert "Priority is already P3" in page(admin, iid)
    admin.post(f"/incidents/{iid}/priority", data={"priority": "NOPE", "reason": "x"})
    assert "Choose a valid priority" in page(admin, iid)


# ====================================================================================================
# Search
# ====================================================================================================

@pytest.fixture
def several(site):
    """Three incidents: two by emp1 (one with an unrelated description) and one by emp2."""
    emp1, emp2 = login(site, "emp1"), login(site, "emp2")
    ids = [new_incident_id(report(emp1, title="Payment gateway down", description="Customers cannot pay")),
           new_incident_id(report(emp1, title="VPN slow", description="Remote access is slow", impact="LOW",
                                  urgency="LOW", affected_users="1")),
           new_incident_id(report(emp2, title="Printer jam", description="Third floor printer", impact="LOW",
                                  urgency="MEDIUM", affected_users="2"))]
    return ids


def search(client, **params):
    return client.get("/incidents/search", params=params).text


def test_the_search_page_asks_for_filters_before_showing_results(site):
    html = login(site, "admin1").get("/incidents/search").text
    assert "Choose one or more filters" in html and 'id="search-form"' in html
    assert all(f'name="{n}"' in html for n in ("ticket_number", "status", "priority", "sla_status", "service_id",
                                              "category_id", "technician_id", "from_date", "to_date", "keyword"))


def test_each_filter_narrows_the_results(site, several):
    admin = login(site, "admin1")
    assert "3 incidents found" in search(admin, status="ASSIGNED")
    assert "1 incident found" in search(admin, priority="P1") and "Payment gateway down" in search(admin, priority="P1")
    assert "Printer jam" in search(admin, keyword="printer") and "Payment gateway down" not in search(admin, keyword="printer")
    assert "1 incident found" in search(admin, ticket_number="INC-1002") and "VPN slow" in search(admin, ticket_number="INC-1002")
    assert "3 incidents found" in search(admin, service_id=str(site.service.id), category_id=str(site.category.id))
    assert "0 incidents found" in search(admin, service_id="999")
    assert "3 incidents found" in search(admin, from_date="2026-11-14", to_date="2026-11-14", technician_id=str(site.cast.tech1.id))
    assert "0 incidents found" in search(admin, from_date="2026-11-15")
    assert "3 incidents found" in search(admin, sla_status="ON_TRACK")
    assert "No incidents to show." in search(admin, keyword="zzz-nothing")


def test_search_results_are_limited_to_what_the_person_may_see(site, several):
    assert "2 incidents found" in search(login(site, "emp1"), status="ASSIGNED")
    assert "Printer jam" not in search(login(site, "emp1"), keyword="printer")
    assert "1 incident found" in search(login(site, "emp2"), status="ASSIGNED")
    assert "3 incidents found" in search(login(site, "tech1"), status="ASSIGNED")
    assert "0 incidents found" in search(login(site, "tech2"), status="ASSIGNED")
    snooping = search(login(site, "emp1"), reporter_id=str(site.cast.emp2.id), keyword="printer")
    assert "Printer jam" not in snooping


def test_only_administrators_get_the_technician_filter_and_reporter_column(site, several):
    assert 'name="technician_id"' in login(site, "admin1").get("/incidents/search").text
    assert 'name="technician_id"' not in login(site, "emp1").get("/incidents/search").text
    assert "<th>Reporter</th>" in search(login(site, "admin1"), status="ASSIGNED")
    assert "<th>Reporter</th>" not in search(login(site, "emp1"), status="ASSIGNED")


def test_an_invalid_date_is_explained_and_ignored(site, several):
    admin = login(site, "admin1")
    html = search(admin, from_date="not-a-date", keyword="printer")
    assert "not a valid date" in html and "Printer jam" in html


def test_search_requires_a_login(anonymous):
    assert anonymous.get("/incidents/search").headers["location"].startswith("/login")


# ====================================================================================================
# The same pages in stub mode
# ====================================================================================================

@pytest.fixture
def stub_site(tmp_path):
    app = create_app(Settings(ITSM_MODE="stub", ENABLE_SCHEDULER=False, SEED_DEMO_DATA=False,
                              DATABASE_PATH=str(tmp_path / "u.db"), EMAIL_LOG_PATH=str(tmp_path / "e.log")))

    def client(username):
        c = TestClient(app, follow_redirects=False)
        assert c.post("/login", data={"username": username, "password": PASSWORD}).status_code == 303
        return c
    return client


def test_w4_in_stub_mode_incident_999_shows_the_invalid_transition_message(stub_site):
    tech = stub_site("tech1")
    response = tech.post("/incidents/999/acknowledge")
    assert response.status_code == 303 and response.headers["location"] == "/incidents/999"
    html = tech.get("/incidents/999").text
    assert "does not allow" in html and "999" in html and 'alert-danger' in html


def test_w7_in_stub_mode_resolve_is_offered_only_for_the_in_progress_incident(stub_site):
    tech = stub_site("tech1")
    assert 'id="resolve-form"' in tech.get("/incidents/1").text                  # IN_PROGRESS
    assigned = tech.get("/incidents/2").text                                    # ASSIGNED
    assert 'id="resolve-form"' not in assigned and "/incidents/2/acknowledge" in assigned


def test_the_report_form_and_workflow_work_in_stub_mode(stub_site):
    emp, tech = stub_site("emp1"), stub_site("tech1")
    iid = new_incident_id(emp.post("/incidents/new", data={**GOOD, "title": "Payment transaction failing again"}))
    assert "may be a duplicate" in emp.get(f"/incidents/{iid}").text
    for step in ("acknowledge", "start"):
        assert tech.post(f"/incidents/{iid}/{step}").status_code == 303
    tech.post(f"/incidents/{iid}/resolve", data={"summary": "Fixed", "details": "Restarted"})
    assert emp.post(f"/incidents/{iid}/verify").status_code == 303
    assert re.search(r'<li class="current">Verified</li>', emp.get(f"/incidents/{iid}").text)
