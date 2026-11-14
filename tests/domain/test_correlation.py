from app.domain.enums import IncidentStatus as S, Level
from app.domain.intelligence.correlation_detector import CorrelationDetector
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.snapshot import IncidentSnapshot
from tests.domain.helpers import at, make_employee

DETECTOR = CorrelationDetector()
CATEGORY = Category("Network", "Network issues", "Network", id=3)
NETWORK = ITService("Network", "Network", Level.HIGH, id=1)
PAYMENT = ITService("Payment", "Payments", Level.HIGH, id=2)
EMAIL = ITService("Email", "Email", Level.MEDIUM, id=3)
NOW = at(120)


def build(n, service, minute, status=S.CLASSIFIED):
    return Incident.restore(IncidentSnapshot(
        id=n, ticket_number=f"INC-{1000 + n}", title=f"Problem {n}", description="details",
        reporter=make_employee(), category=CATEGORY, affected_service=service, impact=Level.HIGH,
        urgency=Level.HIGH, affected_users=3, status=status, created_at=at(minute)))


def test_groups_the_last_hour_by_service_and_flags_probable_service_problems():
    incidents = [
        build(1, NETWORK, 90), build(2, NETWORK, 60), build(3, NETWORK, 119), build(4, NETWORK, 70),
        build(5, PAYMENT, 110), build(6, PAYMENT, 100),
        build(7, EMAIL, 100),                                   # alone: no group
    ]
    groups = DETECTOR.find_groups(incidents, NOW)
    assert [g.service.name for g in groups] == ["Network", "Payment"]
    network, payment = groups
    assert network.is_probable_service_problem and not payment.is_probable_service_problem
    assert [i.ticket_number for i in network.incidents] == ["INC-1002", "INC-1004", "INC-1001", "INC-1003"]
    assert len(payment.incidents) == 2


def test_three_incidents_are_the_threshold():
    three = [build(n, NETWORK, 100 + n) for n in (1, 2, 3)]
    assert DETECTOR.find_groups(three, NOW)[0].is_probable_service_problem
    assert not DETECTOR.find_groups(three[:2], NOW)[0].is_probable_service_problem
    assert DETECTOR.find_groups(three[:1], NOW) == []


def test_the_window_is_the_last_sixty_minutes():
    exactly_sixty = [build(1, NETWORK, 60), build(2, NETWORK, 100)]
    assert len(DETECTOR.find_groups(exactly_sixty, NOW)) == 1            # 60 minutes old: still inside
    too_old = [build(1, NETWORK, 59), build(2, NETWORK, 100)]
    assert DETECTOR.find_groups(too_old, NOW) == []                      # 61 minutes old
    future = [build(1, NETWORK, 121), build(2, NETWORK, 100)]
    assert DETECTOR.find_groups(future, NOW) == []


def test_finished_incidents_are_ignored():
    mixed = [build(1, NETWORK, 100), build(2, NETWORK, 105),
             build(3, NETWORK, 106, S.RESOLVED), build(4, NETWORK, 107, S.VERIFIED),
             build(5, NETWORK, 108, S.CLOSED)]
    group = DETECTOR.find_groups(mixed, NOW)[0]
    assert len(group.incidents) == 2 and not group.is_probable_service_problem


def test_probable_problems_are_listed_first():
    incidents = [build(1, PAYMENT, 100), build(2, PAYMENT, 101),
                 build(3, NETWORK, 100), build(4, NETWORK, 101), build(5, NETWORK, 102)]
    assert [g.service.name for g in DETECTOR.find_groups(incidents, NOW)] == ["Network", "Payment"]
