from types import MappingProxyType

from app.domain.enums import Priority


class BusinessRules:
    """Single home for every business constant. Nothing else hard-codes these."""

    # Priority
    LEVEL_MIN = 1
    LEVEL_MAX = 3
    P1_MIN_SCORE = 18
    P2_MIN_SCORE = 9
    P3_MIN_SCORE = 4
    AFFECTED_USERS_BUMP_THRESHOLD = 50

    # SLA: priority -> (response_minutes, resolution_minutes)
    DEFAULT_SLA_TARGET_MINUTES = MappingProxyType({
        Priority.P1: (5, 30),
        Priority.P2: (15, 120),
        Priority.P3: (60, 480),
        Priority.P4: (240, 1440),
    })
    SLA_WARNING_FRACTION = 0.8

    # Assignment
    MAX_ACTIVE_INCIDENTS = 5
    WEIGHT_SKILL = 40
    WEIGHT_LOAD = 30
    WEIGHT_EXPERIENCE = 15
    WEIGHT_SERVICE_HISTORY = 15
    EXPERIENCE_CAP_YEARS = 10
    SERVICE_HISTORY_CAP = 5

    # Duplicates and correlation
    EXACT_RESUBMISSION_WINDOW_MINUTES = 10
    DUPLICATE_LOOKBACK_HOURS = 24
    DUPLICATE_TEXT_WEIGHT = 0.7
    DUPLICATE_SERVICE_WEIGHT = 0.3
    DUPLICATE_THRESHOLD = 0.5
    CORRELATION_MIN_INCIDENTS = 3
    CORRELATION_WINDOW_MINUTES = 60

    # Escalation and scheduling
    ESCALATION_STEP_MINUTES = 10
    SCHEDULER_INTERVAL_SECONDS = 30

    # Security
    MIN_PASSWORD_LENGTH = 8
    DEMO_PASSWORD = "Password@123"
