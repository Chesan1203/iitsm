from app.domain.enums import IncidentStatus
from app.domain.state.incident_state import IncidentState


class IncidentStateFactory:
    @staticmethod
    def for_status(status: IncidentStatus) -> IncidentState:
        raise NotImplementedError("Implemented in task T3")
