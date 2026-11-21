from __future__ import annotations

import logging
from datetime import timedelta

from app.domain.business_rules import BusinessRules
from app.domain.enums import IncidentStatus, Level, NoteType, Priority, Role
from app.domain.exceptions import (
    CategoryNotFoundError, DuplicateIncidentError, IncidentNotFoundError, InvalidInputError,
    MissingSlaConfigurationError, ServiceNotFoundError, TechnicianUnavailableError,
    UserNotFoundError,
)
from app.domain.intelligence.duplicate_detector import DuplicateDetector
from app.domain.models.audit import AuditRecord
from app.domain.models.candidates import RankedTechnician, TechnicianCandidate
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.sla import SlaPolicy
from app.domain.models.user import Technician, User
from app.domain.sla.sla_calculator import SlaCalculator
from app.domain.strategies.assignment import AssignmentStrategy
from app.domain.strategies.priority import PriorityInput
from app.domain.time_provider import TimeProvider
from app.ports.dto import CreateIncidentRequest, IncidentSearchCriteria
from app.ports.repositories import (
    AuditRepository, CategoryRepository, IncidentRepository, ServiceRepository,
    SlaPolicyRepository, UserRepository,
)
from app.ports.services import IncidentService
from app.services.impl.strategy_registry import StrategyRegistry
from app.services.observers.observer_registrar import ObserverRegistrar
from app.services.security.access_policy import AccessPolicy

logger = logging.getLogger(__name__)

MAX_TITLE = 200
MAX_TEXT = 4000


def _clean(text) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


def _limited(text, field: str, max_length: int = MAX_TEXT):
    """Reject absurdly long input. Blank or wrong-typed values are left for the domain object
    to refuse, so the error wording stays in one place."""
    if isinstance(text, str) and len(text) > max_length:
        raise InvalidInputError(f"{field.replace('_', ' ').capitalize()} must be at most "
                                f"{max_length} characters", field)
    return text


class IncidentServiceImpl(IncidentService):
    """The incident workflow. It orchestrates (load, check access, call the domain, save) but
    contains no business rules: whether an action is legal is decided by the incident's state
    objects, and who may perform it by the domain's permission checks."""

    def __init__(self, incidents: IncidentRepository, users: UserRepository,
                 categories: CategoryRepository, services: ServiceRepository,
                 policies: SlaPolicyRepository, audits: AuditRepository,
                 priority_strategies: StrategyRegistry, assignment_strategies: StrategyRegistry,
                 fallback_assignment: AssignmentStrategy, recommender: AssignmentStrategy,
                 sla_calculator: SlaCalculator, duplicate_detector: DuplicateDetector,
                 time_provider: TimeProvider, registrar: ObserverRegistrar, access: AccessPolicy):
        self._incidents, self._users, self._categories = incidents, users, categories
        self._services, self._policies, self._audits = services, policies, audits
        self._priority, self._assignment = priority_strategies, assignment_strategies
        self._fallback, self._recommender = fallback_assignment, recommender
        self._sla, self._detector = sla_calculator, duplicate_detector
        self._time, self._registrar, self._access = time_provider, registrar, access

    # ====================================================================================
    # Creating an incident
    # ====================================================================================
    def create_incident(self, actor: User, request: CreateIncidentRequest) -> Incident:
        """Report, classify, prioritise, set the SLA and (if possible) assign, in one request.

        Everything that can fail on configuration or input (service, category, SLA policy,
        priority) is worked out BEFORE the first save, so a failure leaves nothing behind."""
        reporter = self._access.require_user(actor)
        now = self._time.now()
        title, description = self._validate_new_incident(request)
        service = self._active_service(request.service_id)
        category = self._active_category(request.category_id)
        self._reject_exact_resubmission(reporter, title, service, now)

        incident = Incident(title, description, reporter, category, service, request.impact,
                            request.urgency, request.affected_users, now)
        priority_result = self._priority.active().calculate(PriorityInput(
            request.impact, request.urgency, service.business_criticality, request.affected_users))
        tracker = self._sla.create_tracker(priority_result.priority, self._policy_for(service), now)

        self._incidents.save(incident)                    # first save: id and ticket number
        self._registrar.attach(incident)
        incident.record_creation(reporter, now)
        self._flag_possible_duplicate(incident, now)
        incident.classify(User.system(), now, priority_result, tracker)
        self._incidents.save(incident)
        self._try_auto_assign(incident, now)
        return incident

    @staticmethod
    def _validate_new_incident(request: CreateIncidentRequest) -> tuple[str, str]:
        title = _clean(_limited(request.title, "title", MAX_TITLE))
        description = _clean(_limited(request.description, "description"))
        if not title:
            raise InvalidInputError("Title is required", "title")
        if not description:
            raise InvalidInputError("Description is required", "description")
        if isinstance(request.affected_users, bool) or not isinstance(request.affected_users, int) \
                or request.affected_users < 1:
            raise InvalidInputError("Affected users must be a whole number of at least 1", "affected_users")
        for value, field in ((request.impact, "impact"), (request.urgency, "urgency")):
            if not isinstance(value, Level):
                raise InvalidInputError(f"Choose a valid {field}", field)
        return title, description

    def _active_service(self, service_id) -> ITService:
        service = self._services.find_by_id(service_id) if isinstance(service_id, int) else None
        if service is None or not service.active:
            raise ServiceNotFoundError("The selected service was not found")
        return service

    def _active_category(self, category_id):
        category = self._categories.find_by_id(category_id) if isinstance(category_id, int) else None
        if category is None or not category.active:
            raise CategoryNotFoundError("The selected category was not found")
        return category

    def _reject_exact_resubmission(self, reporter: User, title: str, service: ITService, now) -> None:
        since = now - timedelta(minutes=BusinessRules.EXACT_RESUBMISSION_WINDOW_MINUTES)
        for earlier in self._incidents.find_recent_by_reporter(reporter.id, since):
            if (earlier.affected_service.id == service.id
                    and _clean(earlier.title).casefold() == title.casefold()):
                raise DuplicateIncidentError(
                    f"You already reported this a moment ago ({earlier.ticket_number})")

    def _policy_for(self, service: ITService) -> SlaPolicy:
        """The service's own policy, else the default policy, else an error."""
        policy = self._policies.find_by_id(service.sla_policy_id) if service.sla_policy_id else None
        policy = policy or self._policies.find_default()
        if policy is None:
            raise MissingSlaConfigurationError(
                f"No SLA policy is set for {service.name} and there is no default policy")
        return policy

    def _flag_possible_duplicate(self, incident: Incident, now) -> None:
        """Compare with open incidents on the same service from the last 24 hours. Flag only."""
        since = now - timedelta(hours=BusinessRules.DUPLICATE_LOOKBACK_HOURS)
        recent = [i for i in self._incidents.find_recent_by_service(incident.affected_service.id, since)
                  if i.is_open and i.id != incident.id]
        matches = self._detector.find_similar(incident, recent)
        if matches:
            best = matches[0]
            incident.mark_possible_duplicate(User.system(), now, best.other_ticket_number, best.score)

    # ====================================================================================
    # Assignment
    # ====================================================================================
    def _candidates(self, incident: Incident) -> list[TechnicianCandidate]:
        service_id = incident.affected_service.id
        return [TechnicianCandidate(
                    t, self._incidents.count_active_by_technician(t.id),
                    self._incidents.count_resolved_by_technician_on_service(t.id, service_id))
                for t in self._users.find_by_role(Role.TECHNICIAN) if isinstance(t, Technician)]

    def _choose_technician(self, incident: Incident) -> tuple[Technician, int] | None:
        """The active strategy picks. If the skill-based strategy finds nobody, fall back to
        load-based so a free technician without the exact skill can still take the incident."""
        candidates = self._candidates(incident)
        strategy = self._assignment.active()
        chosen = strategy.select(incident, candidates)
        if chosen is None and strategy.name == "skill_based":
            chosen = self._fallback.select(incident, candidates)
        if chosen is None:
            return None
        count = next(c.active_incident_count for c in candidates if c.technician.id == chosen.id)
        return chosen, count

    def _try_auto_assign(self, incident: Incident, now) -> None:
        """During creation, finding nobody is not an error: the incident stays CLASSIFIED and
        an administrator can see it by filtering on that status."""
        choice = self._choose_technician(incident)
        if choice is None:
            logger.info("No technician available for %s; it stays CLASSIFIED", incident.ticket_number)
            return
        technician, count = choice
        incident.assign_to(User.system(), now, technician, count)
        self._incidents.save(incident)

    def auto_assign(self, actor: User, incident_id: int) -> Incident:
        """An administrator asks the active strategy to assign a CLASSIFIED incident."""
        admin = self._access.require_role(actor, Role.ADMINISTRATOR)
        incident = self._load(admin, incident_id)
        choice = self._choose_technician(incident)
        if choice is None:
            raise TechnicianUnavailableError("No technician is currently available for this incident")
        technician, count = choice
        incident.assign_to(admin, self._time.now(), technician, count)
        return self._incidents.save(incident)

    def assign(self, actor: User, incident_id: int, technician_id: int) -> Incident:
        """Assign a CLASSIFIED incident, or reassign an ASSIGNED one, to a chosen technician."""
        admin = self._access.require_role(actor, Role.ADMINISTRATOR)
        incident = self._load(admin, incident_id)
        technician = self._users.find_by_id(technician_id)
        if technician is None:
            raise UserNotFoundError(f"User {technician_id} was not found")
        if not isinstance(technician, Technician):
            raise InvalidInputError("The chosen user is not a technician", "technician_id")
        if not technician.active:
            raise TechnicianUnavailableError(f"{technician.full_name}'s account is deactivated")
        count = self._incidents.count_active_by_technician(technician.id)
        now = self._time.now()
        if incident.status is IncidentStatus.CLASSIFIED:
            incident.assign_to(admin, now, technician, count)
        else:
            incident.reassign(admin, now, technician, count)      # the state decides if that is legal
        return self._incidents.save(incident)

    def recommend_technicians(self, actor: User, incident_id: int) -> list[RankedTechnician]:
        admin = self._access.require_role(actor, Role.ADMINISTRATOR)
        incident = self._load(admin, incident_id)
        return self._recommender.rank(incident, self._candidates(incident))

    # ====================================================================================
    # Reading
    # ====================================================================================
    def get_incident(self, actor: User, incident_id: int) -> Incident:
        incident = self._find(incident_id)
        self._access.require_can_view(actor, incident)
        return incident

    def search(self, actor: User, criteria: IncidentSearchCriteria) -> list[Incident]:
        return self._incidents.search(self._access.scope_criteria(actor, criteria))

    def get_audit_trail(self, actor: User, incident_id: int) -> list[AuditRecord]:
        incident = self._find(incident_id)
        self._access.require_can_view(actor, incident)
        return self._audits.find_by_incident(incident.id)

    # ====================================================================================
    # Lifecycle actions: load, check access, call the domain method, save
    # ====================================================================================
    def acknowledge(self, actor: User, incident_id: int) -> Incident:
        return self._act(actor, incident_id, lambda i, now: i.acknowledge(actor, now))

    def start_investigation(self, actor: User, incident_id: int) -> Incident:
        return self._act(actor, incident_id, lambda i, now: i.start_investigation(actor, now))

    def add_note(self, actor: User, incident_id: int, text: str) -> Incident:
        """The assigned technician adds an investigation note; the reporter adds additional
        information (stored as an information response)."""
        _limited(text, "text")

        def add(incident: Incident, now) -> None:
            tech = incident.assigned_technician
            is_reporter = actor.id == incident.reporter.id
            is_technician = tech is not None and actor.id == tech.id
            kind = NoteType.INFO_RESPONSE if is_reporter and not is_technician else NoteType.INVESTIGATION
            incident.add_note(actor, now, text, kind)
        return self._act(actor, incident_id, add)

    def request_info(self, actor: User, incident_id: int, question: str) -> Incident:
        _limited(question, "question")
        return self._act(actor, incident_id, lambda i, now: i.request_info(actor, now, question))

    def respond_to_info_request(self, actor: User, incident_id: int, answer: str) -> Incident:
        _limited(answer, "answer")
        return self._act(actor, incident_id, lambda i, now: i.respond_to_info(actor, now, answer))

    def resolve(self, actor: User, incident_id: int, summary: str, details: str) -> Incident:
        _limited(summary, "summary", MAX_TITLE)
        _limited(details, "details")
        return self._act(actor, incident_id, lambda i, now: i.resolve(actor, now, summary, details))

    def verify(self, actor: User, incident_id: int) -> Incident:
        return self._act(actor, incident_id, lambda i, now: i.verify(actor, now))

    def reject_resolution(self, actor: User, incident_id: int, reason: str) -> Incident:
        _limited(reason, "reason")
        return self._act(actor, incident_id, lambda i, now: i.reject_resolution(actor, now, reason))

    def close(self, actor: User, incident_id: int) -> Incident:
        return self._act(actor, incident_id, lambda i, now: i.close(actor, now))

    def submit_feedback(self, actor: User, incident_id: int, rating: int, comment: str) -> Incident:
        _limited(comment, "comment")
        return self._act(actor, incident_id,
                         lambda i, now: i.submit_feedback(actor, now, rating, comment))

    def override_priority(self, actor: User, incident_id: int, priority: Priority, reason: str) -> Incident:
        """An administrator changes the priority; the deadlines are recalculated from the
        incident's creation time under the new priority."""
        admin = self._access.require_role(actor, Role.ADMINISTRATOR)
        _limited(reason, "reason")
        incident = self._load(admin, incident_id)
        if not isinstance(priority, Priority):
            raise InvalidInputError("Choose a valid priority", "priority")
        tracker = self._sla.create_tracker(priority, self._policy_for(incident.affected_service),
                                           incident.created_at)
        incident.change_priority(admin, self._time.now(), priority, reason, tracker)
        return self._incidents.save(incident)

    # ---- shared steps ------------------------------------------------------------------------------
    def _find(self, incident_id: int) -> Incident:
        incident = self._incidents.find_by_id(incident_id) if isinstance(incident_id, int) else None
        if incident is None:
            raise IncidentNotFoundError(f"Incident {incident_id} was not found")
        return incident

    def _load(self, actor: User, incident_id: int) -> Incident:
        """Load, re-attach the observers (they are never stored), and check the actor may see it."""
        incident = self._registrar.attach(self._find(incident_id))
        self._access.require_can_view(actor, incident)
        return incident

    def _act(self, actor: User, incident_id: int, action) -> Incident:
        incident = self._load(actor, incident_id)
        action(incident, self._time.now())
        return self._incidents.save(incident)
