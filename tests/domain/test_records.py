import dataclasses

import pytest

from app.domain.enums import ChannelType, IncidentEventType, IncidentStatus, NoteType, SlaEventType
from app.domain.exceptions import InvalidInputError
from app.domain.models.audit import AuditRecord
from app.domain.models.incident_parts import Feedback, InvestigationNote, Resolution
from app.domain.models.notification import Notification
from app.domain.models.sla import SlaEvent
from tests.domain.helpers import T0, make_employee, make_technician


def audit(**overrides):
    fields = dict(incident_id=1, ticket_number="INC-1001", timestamp=T0, actor_id=2,
                  actor_name="Ravi K", action="ASSIGNED")
    fields.update(overrides)
    return AuditRecord(**fields)


def notification(**overrides):
    fields = dict(recipient_id=1, incident_id=1, event_type=IncidentEventType.ASSIGNED,
                  channel=ChannelType.IN_APP, message="Assigned to you", created_at=T0)
    fields.update(overrides)
    return Notification(**fields)


def test_audit_record_defaults_and_id_assignment_by_replacement():
    record = audit()
    assert record.id is None and record.previous_status is None and record.description == ""
    saved = dataclasses.replace(record, id=7)
    assert saved.id == 7 and record.id is None                      # the original is untouched
    full = audit(previous_status=IncidentStatus.NEW, new_status=IncidentStatus.CLASSIFIED,
                 description="Classified as Database")
    assert (full.previous_status, full.new_status) == (IncidentStatus.NEW, IncidentStatus.CLASSIFIED)


def test_audit_record_validation_and_immutability():
    for bad in ({"ticket_number": " "}, {"actor_name": ""}, {"action": None}, {"timestamp": "now"}):
        with pytest.raises(InvalidInputError):
            audit(**bad)
    with pytest.raises(dataclasses.FrozenInstanceError):
        audit().action = "TAMPERED"


def test_records_must_be_built_with_keywords():
    with pytest.raises(TypeError):
        AuditRecord(1, "INC-1001", T0, 2, "Ravi", "ASSIGNED")
    with pytest.raises(TypeError):
        Notification(1, 1, IncidentEventType.ASSIGNED, ChannelType.EMAIL, "m", T0)


def test_notification_defaults_validation_and_read_flag():
    n = notification()
    assert n.is_read is False and n.id is None
    assert dataclasses.replace(n, is_read=True, id=3).is_read is True and n.is_read is False
    for bad in ({"event_type": "ASSIGNED"}, {"channel": "EMAIL"}, {"message": "  "}, {"created_at": None}):
        with pytest.raises(InvalidInputError):
            notification(**bad)


def test_sla_event_validation():
    event = SlaEvent(incident_id=1, event_type=SlaEventType.RESPONSE_WARNING, recorded_at=T0)
    assert event.id is None
    for bad in ({"event_type": "WARNING"}, {"recorded_at": "later"}):
        with pytest.raises(InvalidInputError):
            SlaEvent(**{**dict(incident_id=1, event_type=SlaEventType.RESPONSE_WARNING, recorded_at=T0), **bad})


def test_incident_parts_validate_and_are_immutable():
    tech, emp = make_technician(), make_employee()
    note = InvestigationNote(author=tech, note_type=NoteType.INVESTIGATION, text="Checked logs", created_at=T0)
    for bad in ({"text": ""}, {"author": "tech1"}, {"note_type": "INVESTIGATION"}, {"created_at": 5}):
        with pytest.raises(InvalidInputError):
            InvestigationNote(**{**dict(author=tech, note_type=NoteType.INVESTIGATION, text="t", created_at=T0), **bad})
    with pytest.raises(dataclasses.FrozenInstanceError):
        note.text = "edited"
    for bad in (("", "d", tech, T0), ("s", "d", "tech", T0), ("s", "d", tech, "now")):
        with pytest.raises(InvalidInputError):
            Resolution(*bad)
    assert Resolution("Fixed", None, tech, T0).summary == "Fixed"
    with pytest.raises(InvalidInputError):
        Feedback(3, "ok", "yesterday")
    assert Feedback(3, None, T0).rating == 3 and emp.id == 1
