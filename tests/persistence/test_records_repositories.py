"""P2 T3 part 3: audit records, notifications and SLA events."""
from datetime import date

import pytest

from app.domain.enums import ChannelType, IncidentEventType, IncidentStatus, SlaEventType
from app.domain.exceptions import PersistenceError
from app.domain.models.audit import AuditRecord
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent
from app.ports.dto import AuditFilter

from .conftest import at


def _audit(incident, action="CREATED", minutes=0, actor_id=0, actor_name="System", prev=None,
           new=IncidentStatus.NEW):
    return AuditRecord(incident_id=incident.id, ticket_number=incident.ticket_number,
                       timestamp=at(minutes), actor_id=actor_id, actor_name=actor_name,
                       action=action, previous_status=prev, new_status=new, description=f"{action} done")


# ---- audit ---------------------------------------------------------------------------

def test_audit_save_returns_copy_with_id_and_round_trips(world):
    incident = world.new_incident()
    saved = world.audits.save(_audit(incident))
    assert saved.id is not None
    assert world.audits.find_by_incident(incident.id) == [saved]


def test_audit_history_is_oldest_first_and_system_actor_is_allowed(world):
    incident = world.new_incident()
    world.audits.save(_audit(incident, "CLASSIFIED", 2, prev=IncidentStatus.NEW,
                             new=IncidentStatus.CLASSIFIED))
    world.audits.save(_audit(incident, "CREATED", 1))
    history = world.audits.find_by_incident(incident.id)
    assert [r.action for r in history] == ["CREATED", "CLASSIFIED"]
    assert history[0].actor_id == 0 and history[1].previous_status is IncidentStatus.NEW


def test_audit_search_filters_combine_and_newest_first(world):
    one, two = world.new_incident("One"), world.new_incident("Two")
    world.audits.save(_audit(one, "CREATED", 1))
    world.audits.save(_audit(one, "ASSIGNED", 2, actor_id=world.admin.id, actor_name="Meera"))
    world.audits.save(_audit(two, "CREATED", 3))
    assert [r.action for r in world.audits.search(AuditFilter(incident_id=one.id))] == ["ASSIGNED", "CREATED"]
    assert len(world.audits.search(AuditFilter(action="CREATED"))) == 2
    assert len(world.audits.search(AuditFilter(actor_id=world.admin.id))) == 1
    assert len(world.audits.search(AuditFilter(from_date=date(2026, 11, 14), to_date=date(2026, 11, 14)))) == 3
    assert world.audits.search(AuditFilter(from_date=date(2026, 11, 15))) == []
    assert len(world.audits.search(AuditFilter())) == 3


# ---- notifications ---------------------------------------------------------------------

def _note(world, minutes=0, user=None, message="Hello", incident_id=1):
    return Notification(recipient_id=(user or world.reporter).id, incident_id=incident_id,
                        event_type=IncidentEventType.CREATED, channel=ChannelType.IN_APP,
                        message=message, created_at=at(minutes))


def test_notification_save_and_list_newest_first_with_limit(world):
    world.new_incident()
    for i in range(3):
        world.notifications.save(_note(world, i, message=f"m{i}"))
    listed = world.notifications.find_by_recipient(world.reporter.id, 2)
    assert [n.message for n in listed] == ["m2", "m1"]
    assert listed[0].id is not None and listed[0].is_read is False


def test_unread_count_mark_read_and_mark_all_read_only_touch_that_user(world):
    world.new_incident()
    first = world.notifications.save(_note(world, 1))
    world.notifications.save(_note(world, 2))
    world.notifications.save(_note(world, 3, user=world.technician))
    assert world.notifications.count_unread(world.reporter.id) == 2
    world.notifications.mark_read(first.id)
    assert world.notifications.count_unread(world.reporter.id) == 1
    world.notifications.mark_all_read(world.reporter.id)
    assert world.notifications.count_unread(world.reporter.id) == 0
    assert world.notifications.count_unread(world.technician.id) == 1


def test_notification_for_unknown_recipient_is_rejected(world):
    with pytest.raises(PersistenceError):
        world.notifications.save(Notification(
            recipient_id=999, incident_id=1, event_type=IncidentEventType.CREATED,
            channel=ChannelType.EMAIL, message="x", created_at=at(0)))


# ---- SLA events --------------------------------------------------------------------------

def test_sla_event_save_exists_and_list(world):
    incident = world.new_incident()
    assert not world.sla_events.exists(incident.id, SlaEventType.RESPONSE_WARNING)
    saved = world.sla_events.save(SlaEvent(incident_id=incident.id,
                                           event_type=SlaEventType.RESPONSE_WARNING, recorded_at=at(4)))
    assert saved.id is not None
    assert world.sla_events.exists(incident.id, SlaEventType.RESPONSE_WARNING)
    assert not world.sla_events.exists(incident.id, SlaEventType.RESPONSE_VIOLATED)
    assert world.sla_events.find_by_incident(incident.id) == [saved]


def test_same_sla_event_twice_raises_persistence_error(world):
    incident = world.new_incident()
    event = SlaEvent(incident_id=incident.id, event_type=SlaEventType.RESOLUTION_VIOLATED, recorded_at=at(31))
    world.sla_events.save(event)
    with pytest.raises(PersistenceError):
        world.sla_events.save(event)
    assert len(world.sla_events.find_by_incident(incident.id)) == 1
