"""P3 T3: audit observer, notification channels, notification observer and registrar."""
from types import SimpleNamespace

import pytest

from app.domain.enums import (
    AdminLevel,
    ChannelType,
    EscalationLevel,
    IncidentStatus,
    NoteType,
    Priority,
    SlaEventType,
    SlaStatus,
)
from app.domain.enums import (
    IncidentEventType as E,
)
from app.domain.intelligence.escalation_policy import EscalationDecision
from app.domain.models.incident_parts import SlaTracker
from app.domain.models.user import User
from app.domain.sla.sla_calculator import SlaCheckResult
from app.domain.strategies.priority import PriorityResult
from app.services.channels.in_app_channel import InAppChannel
from app.services.channels.notification_channel import NotificationChannel
from app.services.channels.simulated_email_channel import SimulatedEmailChannel
from app.services.observers.audit_observer import AuditObserver
from app.services.observers.notification_observer import NotificationObserver
from app.services.observers.observer_registrar import ObserverRegistrar

from .helpers import ManualTime, RecordingChannel, at, new_incident


class ExplodingChannel(NotificationChannel):
    @property
    def channel_type(self):
        return ChannelType.EMAIL

    def send(self, recipient, incident, event_type, message):
        raise ConnectionError("mail server is down")


@pytest.fixture
def rig(repos, world, tmp_path):
    """Both real channels, a recording channel, both observers and a registrar."""
    clock = ManualTime(at(0))
    log = tmp_path / "logs" / "emails.log"
    recording = RecordingChannel()
    in_app, email = InAppChannel(repos.notifications, clock), SimulatedEmailChannel(log, clock)
    notifier = NotificationObserver(repos.users, [in_app, email, recording])
    registrar = ObserverRegistrar([AuditObserver(repos.audits), notifier])
    return SimpleNamespace(world=world, repos=repos, log=log, recording=recording,
                           registrar=registrar, clock=clock)


def _incident(rig, **kwargs):
    incident = new_incident(rig.world, **kwargs)
    return rig.registrar.attach(incident)


def _tracker(minutes=0):
    return SlaTracker(at(minutes + 5), at(minutes + 30))


# ---- one event, both channels, one audit record -------------------------------------------------------

def test_creating_an_incident_writes_an_audit_record_and_notifies_on_both_channels(rig):
    w = rig.world
    incident = _incident(rig)
    incident.record_creation(w.reporter, at(0))

    trail = rig.repos.audits.find_by_incident(incident.id)
    assert len(trail) == 1
    record = trail[0]
    assert (record.action, record.ticket_number, record.actor_name) == ("CREATED", "INC-1001", "Asha Rao")
    assert record.new_status is IncidentStatus.NEW and record.timestamp == at(0)

    expected = {"emp1", "admin1", "admin2", "admin3"}                 # reporter + every administrator
    in_app = {rig.repos.users.find_by_id(n.recipient_id).username for n in rig.repos.notifications.all()}
    assert in_app == expected and all(n.channel is ChannelType.IN_APP for n in rig.repos.notifications.all())
    log = rig.log.read_text(encoding="utf-8")
    assert log.count("=== Simulated email ===") == 4
    assert "Subject: [INC-1001] Created" in log and "To:      Asha Rao <emp1@x.com>" in log
    assert "Incident INC-1001 was created: Payment down" in log


def test_notification_message_is_friendly_and_names_the_incident(rig):
    incident = _incident(rig)
    incident.record_creation(rig.world.reporter, at(0))
    messages = {n.message for n in rig.repos.notifications.all()}
    assert messages == {"Incident INC-1001 was created: Payment down"}


# ---- who is told, event by event (the plan's table) ----------------------------------------------------------

def test_recipients_for_every_step_of_the_normal_lifecycle(rig):
    w, rec = rig.world, rig.recording
    incident = _incident(rig)
    admins = {"admin1", "admin2", "admin3"}
    steps = [
        (lambda: incident.record_creation(w.reporter, at(0)), E.CREATED, {"emp1"} | admins),
        (lambda: incident.classify(User.system(), at(1), PriorityResult(27, Priority.P1, "x"), _tracker()), E.CLASSIFIED, set()),
        (lambda: incident.assign_to(User.system(), at(2), w.tech, 0), E.ASSIGNED, {"tech1", "emp1"}),
        (lambda: incident.acknowledge(w.tech, at(3)), E.ACKNOWLEDGED, {"emp1"}),
        (lambda: incident.start_investigation(w.tech, at(4)), E.INVESTIGATION_STARTED, set()),
        (lambda: incident.add_note(w.tech, at(5), "Checking logs", NoteType.INVESTIGATION), E.NOTE_ADDED, set()),
        (lambda: incident.request_info(w.tech, at(6), "Which version?"), E.INFO_REQUESTED, {"emp1"}),
        (lambda: incident.respond_to_info(w.reporter, at(7), "Version 2"), E.INFO_RESPONDED, {"tech1"}),
        (lambda: incident.resolve(w.tech, at(8), "Fixed", "Details"), E.RESOLVED, {"emp1"}),
        (lambda: incident.reject_resolution(w.reporter, at(9), "Still broken"), E.RESOLUTION_REJECTED, {"tech1"}),
        (lambda: incident.resolve(w.tech, at(10), "Fixed again", "Details"), E.RESOLVED, {"emp1"}),
        (lambda: incident.verify(w.reporter, at(11)), E.VERIFIED, {"tech1"}),
        (lambda: incident.close(w.reporter, at(12)), E.CLOSED, {"emp1", "tech1"}),
        (lambda: incident.submit_feedback(w.reporter, at(13), 5, "Thanks"), E.FEEDBACK_SUBMITTED, set()),
    ]
    for action, event_type, expected in steps:
        before = len(rec.sent)
        action()
        told = {name for kind, name, _ in rec.sent[before:] if kind is event_type}
        assert told == expected, event_type.name
        assert len(rec.sent) - before == len(expected)               # nobody told about anything else
    assert [r.action for r in rig.repos.audits.find_by_incident(incident.id)][:3] == ["CREATED", "CLASSIFIED", "ASSIGNED"]
    assert len(rig.repos.audits.find_by_incident(incident.id)) == len(steps)      # audit covers every event, even silent ones


def test_recipients_for_reassignment_priority_sla_duplicate_and_escalation(rig):
    w, rec = rig.world, rig.recording
    incident = _incident(rig)
    incident.classify(User.system(), at(1), PriorityResult(27, Priority.P1, "x"), _tracker())
    incident.assign_to(User.system(), at(2), w.tech, 0)

    incident.reassign(w.admin, at(3), w.tech2, 0)
    assert rec.recipients_of(E.REASSIGNED) == {"tech2", "emp1"}

    incident.change_priority(w.admin, at(4), Priority.P2, "less urgent", _tracker(4))
    assert rec.recipients_of(E.PRIORITY_CHANGED) == {"tech2", "emp1"}

    incident.mark_possible_duplicate(User.system(), at(5), "INC-1000", 0.8)
    assert rec.recipients_of(E.DUPLICATE_FLAGGED) == {"admin1", "admin2", "admin3"}

    incident.apply_sla_result(at(6), SlaCheckResult(SlaStatus.WARNING, [SlaEventType.RESPONSE_WARNING]))
    assert rec.recipients_of(E.SLA_WARNING) == {"tech2", "admin1", "admin2", "admin3"}
    incident.apply_sla_result(at(40), SlaCheckResult(SlaStatus.VIOLATED, [SlaEventType.RESPONSE_VIOLATED]))
    assert rec.recipients_of(E.SLA_VIOLATED) == {"tech2", "admin1", "admin2", "admin3"}

    incident.escalate(User.system(), at(41), EscalationDecision(EscalationLevel.SYSTEM_ADMIN, AdminLevel.SYSTEM_ADMIN, "late"))
    assert rec.recipients_of(E.ESCALATED) == {"admin2", "tech2"}       # only administrators at that level


def test_a_reporter_who_is_also_an_administrator_is_notified_once(rig):
    incident = _incident(rig, reporter=rig.world.admin)
    incident.record_creation(rig.world.admin, at(0))
    names = [name for kind, name, _ in rig.recording.sent if kind is E.CREATED]
    assert sorted(names) == ["admin1", "admin2", "admin3"]


def test_deactivated_users_are_not_notified(rig):
    admin2 = rig.repos.users.find_by_username("admin2")
    admin2.deactivate()
    rig.repos.users.save(admin2)
    incident = _incident(rig)
    incident.record_creation(rig.world.reporter, at(0))
    assert rig.recording.recipients_of(E.CREATED) == {"emp1", "admin1", "admin3"}


# ---- failures must not spread -------------------------------------------------------------------------------------

def test_a_failing_channel_does_not_stop_the_others_or_the_audit_or_the_incident(repos, world, tmp_path):
    clock, recording = ManualTime(at(0)), RecordingChannel()
    notifier = NotificationObserver(repos.users, [ExplodingChannel(), InAppChannel(repos.notifications, clock), recording])
    registrar = ObserverRegistrar([notifier, AuditObserver(repos.audits)])
    incident = registrar.attach(new_incident(world))
    incident.record_creation(world.reporter, at(0))
    incident.classify(User.system(), at(1), PriorityResult(27, Priority.P1, "x"), _tracker())
    assert incident.status is IncidentStatus.CLASSIFIED                          # the change stood
    assert len(repos.notifications.all()) == 4 and recording.recipients_of(E.CREATED)    # other channels delivered
    assert len(repos.audits.find_by_incident(incident.id)) == 2                  # audit observer still ran


def test_an_unwritable_email_log_does_not_break_the_incident(repos, world, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so the log path below cannot be created")
    clock = ManualTime(at(0))
    notifier = NotificationObserver(repos.users, [SimulatedEmailChannel(blocker / "emails.log", clock),
                                                  InAppChannel(repos.notifications, clock)])
    incident = ObserverRegistrar([notifier]).attach(new_incident(world))
    incident.record_creation(world.reporter, at(0))
    assert len(repos.notifications.all()) == 4


# ---- the registrar -------------------------------------------------------------------------------------------------

def test_a_loaded_incident_has_no_observers_until_the_registrar_attaches_them(rig):
    w = rig.world
    saved = _incident(rig)
    loaded = rig.repos.incidents.find_by_id(saved.id)
    loaded.record_creation(w.reporter, at(0))
    assert rig.repos.audits.find_by_incident(saved.id) == []                       # the trap the plan warns about
    again = rig.repos.incidents.find_by_id(saved.id)
    rig.registrar.attach(again)
    rig.registrar.attach(again)                                                    # attaching twice is harmless
    again.record_creation(w.reporter, at(1))
    assert len(rig.repos.audits.find_by_incident(saved.id)) == 1
