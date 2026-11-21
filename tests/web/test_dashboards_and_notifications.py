"""Web T2 to T6 (first part): the three dashboards, the badges and the notification pages."""
import re
from types import SimpleNamespace

import pytest

from app.domain.enums import ChannelType, IncidentEventType, Level
from app.domain.models.notification import Notification
from tests.services.helpers import T0, request

from .conftest import login


def report(site, actor, title, description=None, **extra):
    """Create an incident through the real service, as the given user."""
    cast = SimpleNamespace(category=site.category, service=site.service)
    return site.container.incidents.create_incident(
        actor, request(cast, title, description or f"Details about {title}", **extra))


def notify(site, user, message="Hello", minutes=0, read=False):
    return site.repos.notifications.save(Notification(
        recipient_id=user.id, incident_id=None, event_type=IncidentEventType.CREATED,
        channel=ChannelType.IN_APP, message=message, created_at=T0, is_read=read))


# ---- employee dashboard ---------------------------------------------------------------------------------------

def test_an_employee_sees_only_their_own_incidents(site):
    report(site, site.cast.emp1, "Payment gateway down")
    report(site, site.cast.emp2, "Printer on floor 3 jammed", impact=Level.LOW, urgency=Level.LOW)
    html = login(site, "emp1").get("/employee/dashboard").text
    assert "Payment gateway down" in html and "Printer on floor 3 jammed" not in html
    assert "INC-1001" in html and "INC-1002" not in html


def test_the_employee_dashboard_shows_status_priority_and_sla_badges_with_the_right_colours(site):
    report(site, site.cast.emp1, "Payment gateway down")                       # P1, assigned, on track
    html = login(site, "emp1").get("/employee/dashboard").text
    assert re.search(r'badge bg-danger" title="Critical">P1<', html)           # P1 red
    assert re.search(r'badge bg-primary">Assigned<', html)
    assert re.search(r'badge bg-success">On track<', html)
    assert "Ravi" not in html and "Tech1" in html                              # the assigned technician is shown


@pytest.mark.parametrize("impact,urgency,users,priority,colour", [
    (Level.HIGH, Level.HIGH, 120, "P1", "bg-danger"), (Level.HIGH, Level.LOW, 10, "P2", "bg-orange"),   # 3x1x3 = 9
    (Level.MEDIUM, Level.MEDIUM, 10, "P2", "bg-orange"), (Level.LOW, Level.MEDIUM, 10, "P3", "bg-warning text-dark"),
    (Level.LOW, Level.LOW, 1, "P4", "bg-secondary")])
def test_priority_badges_use_one_colour_per_priority(site, impact, urgency, users, priority, colour):
    report(site, site.cast.emp1, "Colour check", impact=impact, urgency=urgency, affected_users=users)
    html = login(site, "emp1").get("/employee/dashboard").text
    assert re.search(rf'badge {re.escape(colour)}" title="[A-Za-z]+">{priority}<', html)


def test_the_status_filter_narrows_the_list_and_unknown_values_are_ignored(site):
    report(site, site.cast.emp1, "Payment gateway down")
    client = login(site, "emp1")
    assert "Payment gateway down" in client.get("/employee/dashboard?status=ASSIGNED").text
    closed = client.get("/employee/dashboard?status=CLOSED").text
    assert "Payment gateway down" not in closed and "No incidents to show." in closed
    assert "Payment gateway down" in client.get("/employee/dashboard?status=NOT_A_STATUS").text


def test_a_possible_duplicate_is_marked_in_the_list(site):
    report(site, site.cast.emp2, "Payment application unavailable")
    report(site, site.cast.emp1, "Payment transaction failing")
    assert "duplicate?" in login(site, "emp1").get("/employee/dashboard").text


def test_incident_text_is_escaped_so_scripts_cannot_run(site):
    report(site, site.cast.emp1, "<script>alert('x')</script>")
    html = login(site, "emp1").get("/employee/dashboard").text
    assert "&lt;script&gt;" in html and "<script>alert('x')" not in html


# ---- technician dashboard -----------------------------------------------------------------------------------------

def test_a_technician_sees_their_assigned_incidents_with_the_workload_bar(site):
    report(site, site.cast.emp1, "Payment gateway down")
    report(site, site.cast.emp2, "Settlement report empty", impact=Level.LOW, urgency=Level.LOW, affected_users=1)
    html = login(site, "tech1").get("/tech/dashboard").text
    assert "Payment gateway down" in html and "Settlement report empty" in html
    assert "2 of 5 active incidents" in html and "width: 40%" in html
    other = login(site, "tech2").get("/tech/dashboard").text
    assert "Payment gateway down" not in other and "0 of 5 active incidents" in other


def test_assigned_incidents_are_listed_most_important_first(site):
    report(site, site.cast.emp1, "Low importance thing", impact=Level.LOW, urgency=Level.LOW, affected_users=1)
    report(site, site.cast.emp1, "Critical outage", impact=Level.HIGH, urgency=Level.HIGH)
    html = login(site, "tech1").get("/tech/dashboard").text
    assert html.index("Critical outage") < html.index("Low importance thing")


# ---- administrator dashboard ----------------------------------------------------------------------------------------

def test_the_administrator_dashboard_shows_the_overview_workload_and_services(site):
    report(site, site.cast.emp1, "Payment gateway down")
    report(site, site.cast.emp2, "Settlement report empty", impact=Level.LOW, urgency=Level.LOW, affected_users=1)
    html = login(site, "admin1").get("/admin/dashboard").text
    cards = re.findall(r'<div class="display-6">(\d+)</div>\s*<div class="text-muted small">([^<]+)</div>', html)
    assert {label: int(value) for value, label in cards} == {
        "Total incidents": 2, "Open": 2, "Critical open": 1, "Resolved": 0, "SLA violations": 0}
    assert "Tech1" in html and "2 / 5" in html and "Tech2" in html and "0 / 5" in html
    assert re.search(r"<td>Payment</td><td class=\"text-end\">2</td>", html)


# ---- notifications ----------------------------------------------------------------------------------------------------

def unread_badge(html) -> int:
    return int(re.search(r'id="unread-count">(\d+)<', html).group(1))


def test_the_bell_shows_the_unread_count_on_every_page(site):
    notify(site, site.cast.emp1, "One")
    notify(site, site.cast.emp1, "Two")
    notify(site, site.cast.emp1, "Already read", read=True)
    client = login(site, "emp1")
    assert unread_badge(client.get("/employee/dashboard").text) == 2
    assert unread_badge(client.get("/notifications").text) == 2
    assert unread_badge(login(site, "tech1").get("/tech/dashboard").text) == 0


def test_the_notifications_page_lists_messages_and_unread_ones_are_highlighted(site):
    notify(site, site.cast.emp1, "Fresh message")
    notify(site, site.cast.emp1, "Old message", read=True)
    notify(site, site.cast.emp2, "Someone else's message")
    html = login(site, "emp1").get("/notifications").text
    assert "Fresh message" in html and "Old message" in html and "Someone else's message" not in html
    assert html.count("list-group-item-primary") == 1


def test_marking_one_or_all_notifications_as_read(site):
    first = notify(site, site.cast.emp1, "First")
    notify(site, site.cast.emp1, "Second")
    client = login(site, "emp1")
    response = client.post(f"/notifications/{first.id}/read")
    assert response.status_code == 303 and response.headers["location"] == "/notifications"
    assert unread_badge(client.get("/notifications").text) == 1
    assert client.post("/notifications/read-all").status_code == 303
    assert unread_badge(client.get("/notifications").text) == 0
    assert "Mark all as read" not in client.get("/notifications").text


def test_a_user_cannot_mark_someone_elses_notification(site):
    theirs = notify(site, site.cast.emp2, "Private")
    client = login(site, "emp1")
    assert client.post(f"/notifications/{theirs.id}/read").status_code == 403
    assert client.post("/notifications/999/read").status_code == 403           # unknown id: same answer
    assert site.repos.notifications.count_unread(site.cast.emp2.id) == 1


def test_notification_text_is_escaped(site):
    notify(site, site.cast.emp1, "<img src=x onerror=alert(1)>")
    html = login(site, "emp1").get("/notifications").text
    assert "&lt;img src=x onerror=alert(1)&gt;" in html and "<img src=x" not in html


def test_real_events_reach_the_bell(site):
    report(site, site.cast.emp1, "Payment gateway down")                        # notifies the reporter and every admin
    assert unread_badge(login(site, "emp1").get("/employee/dashboard").text) >= 2
    assert unread_badge(login(site, "admin2").get("/admin/dashboard").text) >= 1
    assert "was created" in login(site, "admin3").get("/notifications").text
