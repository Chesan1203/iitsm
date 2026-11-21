"""P2 T5: report queries, checked against a small hand-made data set."""
from app.domain.enums import Level, Priority, SlaEventType
from app.domain.models.category import Category
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaEvent
from app.persistence.sqlite_report_repository import SqliteReportRepository
from app.ports.dto import OverviewReport

from .conftest import at, new_technician


def _reports(world):
    return SqliteReportRepository(world.db)


def _build(world):
    """6 incidents: NEW, CLASSIFIED P1 (open), ASSIGNED P1, ASSIGNED P4, CLOSED P1, and
    one RESOLVED-only. Returns them in that order."""
    new = world.new_incident("New one")
    p1_classified = world.classify(world.new_incident("P1 classified"), Priority.P1)
    p1_assigned = world.assign(world.classify(world.new_incident("P1 assigned"), Priority.P1))
    p4_assigned = world.assign(world.classify(world.new_incident("P4 assigned"), Priority.P4))
    closed = world.run_full_lifecycle(world.new_incident("Closed one"))
    resolved = world.assign(world.classify(world.new_incident("Resolved only")))
    resolved.acknowledge(world.technician, at(3))
    resolved.start_investigation(world.technician, at(4))
    resolved.resolve(world.technician, at(5), "Fixed", "Details")
    for incident in (p1_classified, p1_assigned, p4_assigned, closed, resolved):
        world.incidents.save(incident)
    return new, p1_classified, p1_assigned, p4_assigned, closed, resolved


def test_overview_numbers_on_an_empty_database(world):
    assert _reports(world).get_overview() == OverviewReport(0, 0, 0, 0, 0)


def test_overview_counts_open_critical_resolved_and_violations(world):
    new, p1_classified, p1_assigned, *_, closed, resolved = _build(world)
    world.sla_events.save(SlaEvent(incident_id=p1_assigned.id,
                                   event_type=SlaEventType.RESPONSE_VIOLATED, recorded_at=at(10)))
    world.sla_events.save(SlaEvent(incident_id=p1_assigned.id,
                                   event_type=SlaEventType.RESOLUTION_VIOLATED, recorded_at=at(40)))
    world.sla_events.save(SlaEvent(incident_id=resolved.id,
                                   event_type=SlaEventType.RESPONSE_WARNING, recorded_at=at(4)))
    overview = _reports(world).get_overview()
    assert overview.total == 6
    assert overview.open == 4                    # NEW, CLASSIFIED, ASSIGNED, ASSIGNED
    assert overview.critical_open == 2           # the two open P1s (CLOSED P1 excluded)
    assert overview.resolved == 2                # RESOLVED + CLOSED
    assert overview.sla_violations == 1          # two violation events, one incident; warning ignored


def test_workload_includes_technicians_with_zero_and_excludes_closed_incidents(world):
    idle = world.users.save(new_technician("tech_idle", max_workload=3))
    _build(world)                                # tech1: 2 ASSIGNED active; CLOSED and RESOLVED do not count
    by_id = {r.technician_id: r for r in _reports(world).get_technician_workload()}
    assert by_id[world.technician.id].active_count == 2
    assert by_id[idle.id].active_count == 0 and by_id[idle.id].max_workload == 3
    assert len(by_id) == 2                       # employees and admins are not listed
    assert _reports(world).get_technician_workload()[0].technician_id == world.technician.id  # busiest first


def test_service_analysis_lists_every_service_largest_first(world):
    quiet = world.services.save(ITService("Printer", "", Level.LOW))
    _build(world)
    rows = _reports(world).get_service_analysis()
    assert [(r.label, r.count) for r in rows] == [("Payment", 6), ("Printer", 0)]
    assert quiet.id is not None


def test_category_analysis_counts_per_category(world):
    world.categories.save(Category("Network", "", "Network"))
    _build(world)
    rows = _reports(world).get_category_analysis()
    assert [(r.label, r.count) for r in rows] == [("Database", 6), ("Network", 0)]


def test_sla_violation_rows_join_incident_and_technician_newest_first(world):
    _, _, p1_assigned, _, closed, _ = _build(world)
    world.sla_events.save(SlaEvent(incident_id=p1_assigned.id,
                                   event_type=SlaEventType.RESPONSE_VIOLATED, recorded_at=at(10)))
    world.sla_events.save(SlaEvent(incident_id=closed.id,
                                   event_type=SlaEventType.RESOLUTION_VIOLATED, recorded_at=at(50)))
    world.sla_events.save(SlaEvent(incident_id=closed.id,
                                   event_type=SlaEventType.RESPONSE_WARNING, recorded_at=at(60)))
    rows = _reports(world).get_sla_violations()
    assert [r.ticket_number for r in rows] == [closed.ticket_number, p1_assigned.ticket_number]
    assert rows[0].event_type is SlaEventType.RESOLUTION_VIOLATED
    assert rows[0].priority is Priority.P1 and rows[0].technician_name == "Ravi K"
    assert rows[1].title == "P1 assigned"


def test_violation_on_an_unassigned_incident_has_no_technician_name(world):
    incident = world.classify(world.new_incident("Nobody yet"))
    world.incidents.save(incident)
    world.sla_events.save(SlaEvent(incident_id=incident.id,
                                   event_type=SlaEventType.RESPONSE_VIOLATED, recorded_at=at(10)))
    assert _reports(world).get_sla_violations()[0].technician_name is None
