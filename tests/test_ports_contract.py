"""Guards the frozen contract: fails if a port loses, gains or renames a method."""
import dataclasses

from app.ports import repositories as repos
from app.ports import services as svcs
from app.ports.container import Container
from app.ports import dto

EXPECTED_REPOSITORIES = {
    "UserRepository": {"save", "find_by_id", "find_by_username", "find_all", "find_by_role",
                       "find_admins_by_level"},
    "ServiceRepository": {"save", "find_by_id", "find_all", "exists_by_name"},
    "CategoryRepository": {"save", "find_by_id", "find_all"},
    "SlaPolicyRepository": {"save", "find_by_id", "find_default", "find_all"},
    "IncidentRepository": {"save", "find_by_id", "find_by_ticket", "search", "find_open",
                           "find_unacknowledged", "find_recent_by_service",
                           "find_recent_by_reporter", "count_active_by_technician",
                           "count_resolved_by_technician_on_service"},
    "AuditRepository": {"save", "find_by_incident", "search"},
    "NotificationRepository": {"save", "find_by_recipient", "count_unread", "mark_read",
                               "mark_all_read"},
    "SlaEventRepository": {"save", "find_by_incident", "exists"},
    "SettingsRepository": {"get", "put"},
    "ReportRepository": {"get_overview", "get_technician_workload", "get_service_analysis",
                         "get_category_analysis", "get_sla_violations"},
}

EXPECTED_SERVICES = {
    "AuthService": {"login", "register_employee", "get_user"},
    "IncidentService": {"create_incident", "get_incident", "search", "assign", "auto_assign",
                        "recommend_technicians", "acknowledge", "start_investigation", "add_note",
                        "request_info", "respond_to_info_request", "resolve", "verify",
                        "reject_resolution", "close", "submit_feedback", "override_priority",
                        "get_audit_trail"},
    "LookupService": {"list_active_services", "list_active_categories", "list_technicians"},
    "AdminService": {"list_users", "create_user", "deactivate_user", "activate_user",
                     "set_technician_availability", "list_services", "create_service",
                     "update_service", "list_categories", "create_category", "update_category",
                     "list_sla_policies", "save_sla_policy", "list_assignment_strategies",
                     "get_assignment_strategy", "set_assignment_strategy",
                     "list_priority_strategies", "get_priority_strategy", "set_priority_strategy",
                     "is_time_simulated", "get_current_time", "advance_time", "reset_time",
                     "run_sla_check_now", "run_escalation_check_now"},
    "ReportService": {"overview", "technician_workload", "service_analysis", "category_analysis",
                      "sla_violations", "audit_log", "correlation_groups"},
    "NotificationService": {"list_for_user", "unread_count", "mark_read", "mark_all_read"},
}


def _check(module, expected):
    for name, methods in expected.items():
        cls = getattr(module, name)
        assert set(cls.__abstractmethods__) == methods, name


def test_repository_interfaces_match_contract():
    _check(repos, EXPECTED_REPOSITORIES)


def test_service_interfaces_match_contract():
    _check(svcs, EXPECTED_SERVICES)


def test_interfaces_cannot_be_instantiated():
    for module, expected in ((repos, EXPECTED_REPOSITORIES), (svcs, EXPECTED_SERVICES)):
        for name in expected:
            try:
                getattr(module, name)()
            except TypeError:
                continue
            raise AssertionError(f"{name} should be abstract")


def test_dto_field_names_match_contract():
    fields = {n: [f.name for f in dataclasses.fields(getattr(dto, n))] for n in (
        "RegisterRequest", "CreateIncidentRequest", "CreateUserRequest", "ServiceRequest",
        "CategoryRequest", "SlaPolicyRequest", "IncidentSearchCriteria", "AuditFilter",
        "OverviewReport", "WorkloadRow", "CountRow", "SlaViolationRow")}
    assert fields["RegisterRequest"] == ["username", "full_name", "email", "password", "department"]
    assert fields["CreateIncidentRequest"] == ["title", "description", "category_id", "service_id",
                                               "impact", "urgency", "affected_users"]
    assert fields["CreateUserRequest"] == ["username", "full_name", "email", "password", "role",
                                           "department", "admin_level", "skills",
                                           "experience_years", "max_workload"]
    assert fields["ServiceRequest"] == ["name", "description", "business_criticality",
                                        "sla_policy_id", "active"]
    assert fields["CategoryRequest"] == ["name", "description", "required_skill", "active"]
    assert fields["SlaPolicyRequest"] == ["name", "is_default", "targets"]
    assert fields["IncidentSearchCriteria"] == ["ticket_number", "status", "priority", "category_id",
                                                "service_id", "technician_id", "reporter_id",
                                                "sla_status", "from_date", "to_date", "keyword"]
    assert fields["AuditFilter"] == ["incident_id", "actor_id", "action", "from_date", "to_date"]
    assert fields["OverviewReport"] == ["total", "open", "critical_open", "resolved", "sla_violations"]
    assert fields["WorkloadRow"] == ["technician_id", "technician_name", "active_count", "max_workload"]
    assert fields["CountRow"] == ["label", "count"]
    assert fields["SlaViolationRow"] == ["ticket_number", "title", "priority", "technician_name",
                                         "event_type", "recorded_at"]


def test_container_has_six_services():
    c = Container()
    assert [a for a in vars(c)] == ["auth", "incidents", "lookup", "admin", "reports", "notifications"]
