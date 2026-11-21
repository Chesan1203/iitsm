# Exception handling

Every application error derives from one base class, `ITSMError` (`app/domain/exceptions.py`), and
carries a human-readable `message`. Code raises these instead of returning error codes, and never
raises a bare `Exception`. `InvalidInputError` also carries the name of the offending `field`.

Services raise them; the web layer turns them into something friendly in one place
(`app/web/errors.py`), except on form pages, which catch `InvalidInputError` themselves so the message
appears next to the field. A raw database error never reaches the user: the persistence layer converts
every `sqlite3` error into `PersistenceError`.

## 1. The exceptions and what the user sees

| Exception | Raised when | Raised in | What the user sees |
| --- | --- | --- | --- |
| `ITSMError` (base) | Never raised directly | n/a | Any subclass without a more specific rule below is shown as a red message on the page they came from |
| `InvalidLoginError` | Unknown user, wrong password or inactive account. The message is always the same generic text. | `AuthServiceImpl.login` | The sign-in page again (HTTP 401) with "Invalid username or password", the username kept, the password never shown |
| `UnauthorizedOperationError` | The actor's role or identity does not allow the action, including a missing or deactivated actor | Domain `state/permissions.py`; `AccessPolicy`; `NotificationServiceImpl.mark_read`; the web role guards | A "You do not have permission to do that" page (HTTP 403). An anonymous visitor is redirected to the sign-in page instead |
| `InvalidStateTransitionError` | An action is not allowed in the incident's current status (for example closing an ASSIGNED incident) | Domain state classes (`incident_state.py`, `states.py`) | Back on the incident page, a red message such as "Cannot close an incident that is ASSIGNED"; nothing changes |
| `TechnicianUnavailableError` | The technician is on leave or deactivated, or no technician is available for an auto-assign | Domain `assign_to` / `reassign`; `IncidentServiceImpl.assign`, `auto_assign` | Back on the incident page, a red message |
| `WorkloadExceededError` | The technician already has the maximum number of active incidents | Domain `assign_to` / `reassign` | Back on the incident page, a red message |
| `NotFoundError` (base of the four below) | A looked-up object does not exist | n/a | A "We could not find that" page (HTTP 404) |
| `IncidentNotFoundError` | The incident id does not exist | `IncidentServiceImpl` | The 404 page |
| `ServiceNotFoundError` | The service is missing or inactive (reporting), or the id is unknown (admin edit) | `IncidentServiceImpl.create_incident`, `AdminServiceImpl.update_service` | On the report form, an error beside the service dropdown (HTTP 400); on an admin edit page, the 404 page |
| `CategoryNotFoundError` | The category is missing or inactive, or the id is unknown (admin edit) | `IncidentServiceImpl.create_incident`, `AdminServiceImpl.update_category` | On the report form, an error beside the category dropdown (HTTP 400); on an admin edit page, the 404 page |
| `UserNotFoundError` | The user id does not exist | `AdminServiceImpl`, `IncidentServiceImpl.assign` | The 404 page |
| `MissingSlaConfigurationError` | No SLA policy for the service and no default policy, or the policy lacks a target for the incident's priority | `SlaPolicy.target_for`; `IncidentServiceImpl` | A red message ("No SLA policy is set for ... and there is no default policy") on the page they came from. Nothing is saved |
| `DuplicateIncidentError` | The same reporter, title and service within the last 10 minutes (an accidental resubmission; the message names the earlier ticket) | `IncidentServiceImpl.create_incident` | The report form again (HTTP 409) with "You already reported this a moment ago (INC-...)", what was typed kept |
| `InvalidInputError` | Bad or missing input; `field` names which one | Domain entities and state classes; `input_rules`; `UserFactory`; `PasswordHasher`; all services; `StrategyRegistry` | On a form: the form again (HTTP 400) with the message beside the named field and the entries kept. A message about a field the form does not have appears in the form's general error area. On an action button (for example Resolve with a blank summary): a red message on the incident page |
| `PersistenceError` | Any database failure: unique or foreign-key violation, unusable path, a missing row on update, inconsistent stored data | Every `Sqlite*Repository` and `Database` | A generic "Something went wrong on our side" page (HTTP 500). The details go to the log only |

## 2. Conditions that belong to the web layer

| Condition | What the user sees |
| --- | --- |
| Not signed in (a missing or invalid session) | A redirect to `/login`, remembering the page asked for |
| An unknown URL | The 404 page |
| A wrong method (for example opening `/logout` as a link) | A "That request is not allowed here" page (HTTP 405) |
| A malformed request, such as a non-numeric id in a notification URL | A "That request could not be understood" page (HTTP 400) |
| Any unexpected error | The generic 500 page. The details and stack trace go to the log; the page shows neither |

## 3. Rules the code follows

- **Order of checks inside every incident action:** first "is this action legal in the current state?"
  (`InvalidStateTransitionError`), then "is this actor allowed?" (`UnauthorizedOperationError`), then "is the
  data valid?" (`InvalidInputError`, or the workload errors). That order makes the error for a given mistake
  predictable and testable.
- **Fail before saving.** Configuration problems (missing SLA policy, unknown service or category) are detected
  before the first save, so they never leave a half-created incident.
- **Recoverable concurrency conflicts are translated.** Two people registering the same username at the same
  moment hit the database's unique rule; the service converts the resulting `PersistenceError` into a normal
  `InvalidInputError` for the username field.
- **A message is never silently lost.** A message that belongs to no field on a form is shown in the form's
  general error area, and messages that are waiting to be shown are kept when another one is added.
- **Background jobs do not raise to the scheduler.** Each incident is processed inside its own error handling; a
  failure is logged and the next incident (and the next run) still happens.
- **Observers and channels are isolated.** A failing notification channel, or an unwritable email log, is logged
  and never prevents the incident change, the audit record or the other channels.
- **Startup configuration errors are `ValueError`.** An invalid setting such as `ITSM_MODE=banana` stops the
  application at start with a clear message, before any request is served.
