from app.domain.enums import IncidentStatus
from app.domain.exceptions import InvalidInputError
from app.domain.state.incident_state import IncidentState
from app.domain.state.states import (
    AcknowledgedState, AssignedState, ClassifiedState, ClosedState, InProgressState,
    NewState, ResolvedState, VerifiedState,
)

# States hold no data, so one shared instance per status is enough.
_STATES: dict[IncidentStatus, IncidentState] = {
    state.status: state
    for state in (NewState(), ClassifiedState(), AssignedState(), AcknowledgedState(),
                  InProgressState(), ResolvedState(), VerifiedState(), ClosedState())
}


class IncidentStateFactory:
    @staticmethod
    def for_status(status: IncidentStatus) -> IncidentState:
        try:
            return _STATES[status]
        except KeyError:
            raise InvalidInputError(f"Unknown incident status: {status!r}", "status") from None
