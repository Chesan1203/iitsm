-- I-ITSM database schema (SQLite). Safe to run repeatedly: every statement is IF NOT EXISTS.
--
-- Storage conventions (the repositories in app/persistence follow these):
--   * dates are ISO text ("2026-11-14 10:05:00"), which also sorts correctly as text
--   * booleans are 0 or 1
--   * enums are stored by member NAME ("P1", "IN_PROGRESS"); Level (impact, urgency,
--     business_criticality) is stored as its number 1..3
--   * foreign keys are only enforced when each connection runs PRAGMA foreign_keys = ON
--     (Database.connection() does that)
--   * audit_records.actor_id has no foreign key on purpose: the system actor has id 0 and
--     is not a row in users

CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL UNIQUE,
    full_name        TEXT    NOT NULL,
    email            TEXT    NOT NULL,
    password_hash    TEXT    NOT NULL,
    role             TEXT    NOT NULL CHECK (role IN ('EMPLOYEE', 'TECHNICIAN', 'ADMINISTRATOR')),
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    -- columns below apply to one role only and stay NULL for the others
    department       TEXT,                                           -- Employee
    admin_level      TEXT CHECK (admin_level IS NULL
                                 OR admin_level IN ('TEAM_LEAD', 'SYSTEM_ADMIN', 'IT_MANAGER')),
    experience_years INTEGER CHECK (experience_years IS NULL OR experience_years >= 0),
    available        INTEGER CHECK (available IS NULL OR available IN (0, 1)),
    max_workload     INTEGER CHECK (max_workload IS NULL OR max_workload >= 0)
);

CREATE TABLE IF NOT EXISTS technician_skills (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    skill   TEXT    NOT NULL,
    PRIMARY KEY (user_id, skill)
);

CREATE TABLE IF NOT EXISTS categories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL UNIQUE,
    description    TEXT    NOT NULL DEFAULT '',
    required_skill TEXT    NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS sla_policies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))
);

CREATE TABLE IF NOT EXISTS sla_targets (
    policy_id          INTEGER NOT NULL REFERENCES sla_policies (id) ON DELETE CASCADE,
    priority           TEXT    NOT NULL CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
    response_minutes   INTEGER NOT NULL CHECK (response_minutes > 0),
    resolution_minutes INTEGER NOT NULL CHECK (resolution_minutes > 0),
    PRIMARY KEY (policy_id, priority)
);

CREATE TABLE IF NOT EXISTS it_services (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL UNIQUE,
    description          TEXT    NOT NULL DEFAULT '',
    business_criticality INTEGER NOT NULL CHECK (business_criticality BETWEEN 1 AND 3),
    sla_policy_id        INTEGER REFERENCES sla_policies (id),       -- NULL = use the default policy
    active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS incidents (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number           TEXT    UNIQUE,                          -- INC-1001; set right after first insert
    title                   TEXT    NOT NULL,
    description             TEXT    NOT NULL,
    reporter_id             INTEGER NOT NULL REFERENCES users (id),
    category_id             INTEGER NOT NULL REFERENCES categories (id),
    service_id              INTEGER NOT NULL REFERENCES it_services (id),
    impact                  INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 3),
    urgency                 INTEGER NOT NULL CHECK (urgency BETWEEN 1 AND 3),
    affected_users          INTEGER NOT NULL CHECK (affected_users >= 0),
    priority                TEXT    CHECK (priority IS NULL OR priority IN ('P1', 'P2', 'P3', 'P4')),
    priority_score          INTEGER,
    status                  TEXT    NOT NULL CHECK (status IN
                                ('NEW', 'CLASSIFIED', 'ASSIGNED', 'ACKNOWLEDGED',
                                 'IN_PROGRESS', 'RESOLVED', 'VERIFIED', 'CLOSED')),
    created_at              TEXT    NOT NULL,
    assigned_technician_id  INTEGER REFERENCES users (id),
    assigned_at             TEXT,
    acknowledged_at         TEXT,
    resolved_at             TEXT,
    verified_at             TEXT,
    closed_at               TEXT,
    escalation_level        TEXT    NOT NULL DEFAULT 'TECHNICIAN' CHECK (escalation_level IN
                                ('TECHNICIAN', 'TEAM_LEAD', 'SYSTEM_ADMIN', 'IT_MANAGER')),
    possible_duplicate_of   TEXT,                                    -- a ticket number, not a foreign key
    -- SLA tracker (all NULL / 0 until the incident is classified)
    sla_status              TEXT    CHECK (sla_status IS NULL
                                           OR sla_status IN ('ON_TRACK', 'WARNING', 'VIOLATED', 'MET')),
    sla_response_deadline   TEXT,
    sla_resolution_deadline TEXT,
    sla_response_warned     INTEGER NOT NULL DEFAULT 0 CHECK (sla_response_warned IN (0, 1)),
    sla_resolution_warned   INTEGER NOT NULL DEFAULT 0 CHECK (sla_resolution_warned IN (0, 1)),
    sla_response_violated   INTEGER NOT NULL DEFAULT 0 CHECK (sla_response_violated IN (0, 1)),
    sla_resolution_violated INTEGER NOT NULL DEFAULT 0 CHECK (sla_resolution_violated IN (0, 1)),
    -- resolution (NULL until resolved)
    resolution_summary      TEXT,
    resolution_details      TEXT,
    resolved_by_id          INTEGER REFERENCES users (id),
    resolution_at           TEXT,                                    -- Resolution.resolved_at (kept separate so nothing is lost)
    -- feedback (NULL until submitted)
    feedback_rating         INTEGER CHECK (feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5),
    feedback_comment        TEXT,
    feedback_at             TEXT
);

CREATE TABLE IF NOT EXISTS incident_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES users (id),
    note_type   TEXT    NOT NULL CHECK (note_type IN ('INVESTIGATION', 'INFO_REQUEST', 'INFO_RESPONSE')),
    text        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id     INTEGER NOT NULL,
    ticket_number   TEXT,
    timestamp       TEXT    NOT NULL,
    actor_id        INTEGER NOT NULL,                                -- 0 = the system actor
    actor_name      TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    previous_status TEXT,
    new_status      TEXT,
    description     TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sla_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    event_type  TEXT    NOT NULL CHECK (event_type IN
                    ('RESPONSE_WARNING', 'RESOLUTION_WARNING',
                     'RESPONSE_VIOLATED', 'RESOLUTION_VIOLATED')),
    recorded_at TEXT    NOT NULL,
    UNIQUE (incident_id, event_type)                                 -- an event is recorded once only
);

CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL REFERENCES users (id),
    incident_id  INTEGER,
    event_type   TEXT    NOT NULL,
    channel      TEXT    NOT NULL CHECK (channel IN ('IN_APP', 'EMAIL')),
    message      TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    is_read      INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes -------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_incidents_status     ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_priority   ON incidents (priority);
CREATE INDEX IF NOT EXISTS idx_incidents_service    ON incidents (service_id);
CREATE INDEX IF NOT EXISTS idx_incidents_category   ON incidents (category_id);
CREATE INDEX IF NOT EXISTS idx_incidents_technician ON incidents (assigned_technician_id);
CREATE INDEX IF NOT EXISTS idx_incidents_reporter   ON incidents (reporter_id);
CREATE INDEX IF NOT EXISTS idx_incidents_created    ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_notes_incident       ON incident_notes (incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_incident       ON audit_records (incident_id);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications (recipient_id);
