"""One class per IncidentStatus. In T3 each overrides only the actions legal in that state
(see the lifecycle table in the plan, section 5.8). Until then every action is illegal."""
from app.domain.enums import IncidentStatus
from app.domain.state.incident_state import IncidentState


class NewState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.NEW


class ClassifiedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.CLASSIFIED


class AssignedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.ASSIGNED


class AcknowledgedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.ACKNOWLEDGED


class InProgressState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.IN_PROGRESS


class ResolvedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.RESOLVED


class VerifiedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.VERIFIED


class ClosedState(IncidentState):
    @property
    def status(self) -> IncidentStatus:
        return IncidentStatus.CLOSED
