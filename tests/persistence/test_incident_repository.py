"""P2 T3 part 2 (+ the T4 search and T5 helper queries the incident repository also carries)."""
from dataclasses import replace
from datetime import date, timedelta

import pytest

from contextlib import contextmanager

from app.domain.enums import IncidentStatus, Level, NoteType, Priority, SlaStatus
from app.domain.exceptions import PersistenceError
from app.domain.models.incident import Incident
from app.domain.models.user import Employee
from app.ports.dto import IncidentSearchCriteria

from .conftest import T0, at, new_employee


def same_incident(a: Incident, b: Incident) -> bool:
    """Equal snapshots, ignoring note ids (notes are re-inserted on every save)."""
    def norm(inc):
        snap = inc.snapshot()
        return replace(snap, notes=tuple(replace(n, id=None) for n in snap.notes))
    return norm(a) == norm(b)


# ---- save and load -------------------------------------------------------------------

def test_first_save_assigns_id_and_ticket_numbers_in_sequence(world):
    first, second = world.new_incident("One"), world.new_incident("Two")
    assert (first.id, first.ticket_number) == (1, "INC-1001")
    assert (second.id, second.ticket_number) == (2, "INC-1002")


def test_new_incident_round_trips(world):
    saved = world.new_incident()
    loaded = world.incidents.find_by_id(saved.id)
    assert same_incident(saved, loaded) and loaded.status is IncidentStatus.NEW
    assert loaded.priority is None and loaded.sla_tracker is None


def test_full_lifecycle_incident_round_trips_with_notes_resolution_feedback_and_tracker(world):
    incident = world.run_full_lifecycle(world.new_incident())
    world.incidents.save(incident)
    loaded = world.incidents.find_by_id(incident.id)
    assert same_incident(incident, loaded)
    assert loaded.status is IncidentStatus.CLOSED
    assert [n.text for n in loaded.notes] == [
        "Checking the connection pool", "Which app version are you on?", "Version 2.3"]
    assert loaded.resolution.summary == "Restarted DB pool"
    assert loaded.resolution.resolved_by == world.technician
    assert loaded.feedback.rating == 5
    assert loaded.sla_tracker == incident.sla_tracker


def test_second_save_updates_the_row_and_replaces_notes_not_duplicates_them(world):
    incident = world.new_incident()
    world.classify(incident)
    world.assign(incident)
    incident.acknowledge(world.technician, at(3))
    incident.start_investigation(world.technician, at(4))
    world.incidents.save(incident)
    world.incidents.save(incident)                          # same state saved again
    incident.add_note(world.technician, at(5), "First note", NoteType.INVESTIGATION)
    world.incidents.save(incident)
    world.incidents.save(incident)
    with world.db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM incident_notes").fetchone()[0] == 1
    assert world.incidents.find_by_id(incident.id).status is IncidentStatus.IN_PROGRESS


def test_loaded_incident_has_no_observers_and_can_be_changed_again(world):
    incident = world.new_incident()
    loaded = world.incidents.find_by_id(incident.id)
    assert loaded._observers == []
    world.classify(loaded)
    world.incidents.save(loaded)
    assert world.incidents.find_by_id(incident.id).status is IncidentStatus.CLASSIFIED


def test_find_by_ticket_and_missing_lookups(world):
    saved = world.new_incident()
    assert world.incidents.find_by_ticket("INC-1001").id == saved.id
    assert world.incidents.find_by_ticket("INC-9999") is None
    assert world.incidents.find_by_id(999) is None


def test_saving_with_an_unsaved_reporter_fails_and_assigns_no_identity(world):
    incident = world.new_incident(reporter=new_employee("unsaved"), save=False)
    with pytest.raises(PersistenceError):
        world.incidents.save(incident)
    assert incident.id is None and incident.ticket_number is None
    with world.db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0


def test_updating_an_incident_that_is_not_in_the_database_raises(world):
    incident = world.new_incident()
    with world.db.connection() as conn:
        conn.execute("DELETE FROM incidents")
    with pytest.raises(PersistenceError):
        world.incidents.save(incident)


def test_loading_a_list_does_not_run_one_query_per_incident(world):
    for n in range(12):                       # 12 open incidents, each with a note
        incident = world.assign(world.classify(world.new_incident(f"Incident {n}")))
        incident.acknowledge(world.technician, at(3))
        incident.start_investigation(world.technician, at(4))
        incident.add_note(world.technician, at(5), f"note {n}", NoteType.INVESTIGATION)
        world.incidents.save(incident)

    statements = []
    real = world.db.connection

    @contextmanager
    def counting():
        with real() as conn:
            conn.set_trace_callback(statements.append)
            yield conn
    world.db.connection = counting
    loaded = world.incidents.find_open()
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(loaded) == 12 and all(len(i.notes) == 1 for i in loaded)
    # incidents, notes, users, technician skills, services, categories: a fixed handful of
    # queries, not one per incident
    assert len(selects) <= 6


# ---- search (T4) -----------------------------------------------------------------------

def _mixed(world):
    a = world.classify(world.new_incident("Payment gateway down", "Users cannot pay"), Priority.P1)
    b = world.classify(world.new_incident("VPN slow", "Remote access is slow", at(60),
                                          impact=Level.LOW, urgency=Level.LOW, users=2), Priority.P4)
    world.incidents.save(a)
    world.incidents.save(b)
    c = world.new_incident("Printer jam", "Floor 3 printer", at(60 * 24 * 3))
    return a, b, c


def test_search_with_no_criteria_returns_everything_newest_first(world):
    a, b, c = _mixed(world)
    assert [i.id for i in world.incidents.search(IncidentSearchCriteria())] == [c.id, b.id, a.id]


def test_search_status_and_priority_narrow_together(world):
    a, b, _ = _mixed(world)
    found = world.incidents.search(IncidentSearchCriteria(status=IncidentStatus.CLASSIFIED,
                                                          priority=Priority.P1))
    assert [i.id for i in found] == [a.id]
    assert world.incidents.search(IncidentSearchCriteria(status=IncidentStatus.NEW,
                                                         priority=Priority.P1)) == []


def test_search_by_ticket_service_category_reporter_technician_and_sla_status(world):
    a, _, _ = _mixed(world)
    world.assign(a)
    world.incidents.save(a)
    for criteria in (IncidentSearchCriteria(ticket_number=a.ticket_number),
                     IncidentSearchCriteria(service_id=world.service.id, technician_id=world.technician.id),
                     IncidentSearchCriteria(category_id=world.category.id, reporter_id=world.reporter.id,
                                            sla_status=SlaStatus.ON_TRACK, technician_id=world.technician.id)):
        assert [i.id for i in world.incidents.search(criteria)] == [a.id]


def test_search_keyword_matches_title_or_description_ignoring_case(world):
    a, b, _ = _mixed(world)
    assert [i.id for i in world.incidents.search(IncidentSearchCriteria(keyword="GATEWAY"))] == [a.id]
    assert [i.id for i in world.incidents.search(IncidentSearchCriteria(keyword="remote"))] == [b.id]
    assert world.incidents.search(IncidentSearchCriteria(keyword="zzz-no-match")) == []


def test_search_date_range_includes_the_whole_end_day(world):
    a, b, c = _mixed(world)                     # a, b on 14 Nov; c on 17 Nov
    day = date(2026, 11, 14)
    assert {i.id for i in world.incidents.search(IncidentSearchCriteria(from_date=day, to_date=day))} == {a.id, b.id}
    assert [i.id for i in world.incidents.search(IncidentSearchCriteria(from_date=date(2026, 11, 15)))] == [c.id]
    assert {i.id for i in world.incidents.search(IncidentSearchCriteria(to_date=day))} == {a.id, b.id}


def test_search_treats_sql_injection_text_as_plain_text(world):
    _mixed(world)
    assert world.incidents.search(IncidentSearchCriteria(keyword="x' OR '1'='1")) == []
    assert world.incidents.search(IncidentSearchCriteria(ticket_number="' OR 1=1 --")) == []
    with world.db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 3


def test_search_percent_and_underscore_are_literal_characters(world):
    world.new_incident("Disk at 100% full", "Server disk")
    world.new_incident("Disk at 100 full", "Server disk")
    found = world.incidents.search(IncidentSearchCriteria(keyword="100%"))
    assert [i.title for i in found] == ["Disk at 100% full"]


# ---- helper queries (T5) ------------------------------------------------------------------

def test_find_open_excludes_only_closed_and_unacknowledged_means_assigned(world):
    open_one = world.assign(world.classify(world.new_incident("Open")))
    world.incidents.save(open_one)
    done = world.run_full_lifecycle(world.new_incident("Done"))
    world.incidents.save(done)
    assert [i.title for i in world.incidents.find_open()] == ["Open"]
    assert [i.title for i in world.incidents.find_unacknowledged()] == ["Open"]


def test_find_recent_by_service_and_reporter_respect_since(world):
    old = world.new_incident("Old", created_at=T0 - timedelta(hours=30))
    recent = world.new_incident("Recent", created_at=T0)
    other = world.users.save(Employee("emp2", "B", "b@x.com", "h"))
    other_inc = world.new_incident("Other person", created_at=T0, reporter=other)
    since = T0 - timedelta(hours=24)
    assert {i.id for i in world.incidents.find_recent_by_service(world.service.id, since)} == {recent.id, other_inc.id}
    assert [i.id for i in world.incidents.find_recent_by_reporter(world.reporter.id, since)] == [recent.id]
    assert old.id not in {i.id for i in world.incidents.find_recent_by_service(world.service.id, since)}


def test_technician_counts_use_the_right_statuses(world):
    active = world.assign(world.classify(world.new_incident("Active")))
    world.incidents.save(active)
    done = world.run_full_lifecycle(world.new_incident("Done"))
    world.incidents.save(done)
    tid, sid = world.technician.id, world.service.id
    assert world.incidents.count_active_by_technician(tid) == 1        # CLOSED does not count
    assert world.incidents.count_resolved_by_technician_on_service(tid, sid) == 1
    assert world.incidents.count_resolved_by_technician_on_service(tid, 999) == 0
    assert world.incidents.count_active_by_technician(world.admin.id) == 0
