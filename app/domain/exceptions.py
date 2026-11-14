class ITSMError(Exception):
    """Base class for every application error. Never raised directly."""

    def __init__(self, message: str):
        super().__init__(message)
        self._message = message

    @property
    def message(self) -> str:
        return self._message

    def __str__(self) -> str:
        return self._message


class InvalidLoginError(ITSMError):
    pass


class UnauthorizedOperationError(ITSMError):
    pass


class InvalidStateTransitionError(ITSMError):
    pass


class TechnicianUnavailableError(ITSMError):
    pass


class WorkloadExceededError(ITSMError):
    pass


class NotFoundError(ITSMError):
    pass


class IncidentNotFoundError(NotFoundError):
    pass


class ServiceNotFoundError(NotFoundError):
    pass


class CategoryNotFoundError(NotFoundError):
    pass


class UserNotFoundError(NotFoundError):
    pass


class MissingSlaConfigurationError(ITSMError):
    pass


class DuplicateIncidentError(ITSMError):
    pass


class InvalidInputError(ITSMError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self._field = field

    @property
    def field(self) -> str | None:
        return self._field


class PersistenceError(ITSMError):
    pass
