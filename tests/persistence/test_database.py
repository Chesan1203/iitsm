"""P2 T1/T2: the schema and the Database helper. Tests use a temporary file, never :memory:."""
import sqlite3

import pytest

from app.domain.exceptions import NotFoundError, PersistenceError
from app.persistence.database import Database

EXPECTED_TABLES = {
    "users", "technician_skills", "categories", "it_services", "sla_policies", "sla_targets",
    "incidents", "incident_notes", "audit_records", "sla_events", "notifications", "settings",
}

USER_SQL = ("INSERT INTO users (username, full_name, email, password_hash, role) "
            "VALUES (?, 'Test User', 't@example.com', 'hash', ?)")


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialise()
    return database


def _tables(database):
    with database.connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def _seed_incident_prerequisites(conn):
    conn.execute(USER_SQL, ("emp", "EMPLOYEE"))
    conn.execute("INSERT INTO categories (name, required_skill) VALUES ('Network', 'Network')")
    conn.execute("INSERT INTO it_services (name, business_criticality) VALUES ('VPN', 2)")


INCIDENT_SQL = ("INSERT INTO incidents (ticket_number, title, description, reporter_id, category_id, "
                "service_id, impact, urgency, affected_users, status, created_at) "
                "VALUES (?, 'Title', 'Desc', 1, 1, 1, 2, 2, 1, 'NEW', '2026-11-14 10:00:00')")


# ---- schema ------------------------------------------------------------------

def test_initialise_creates_every_table(db):
    assert EXPECTED_TABLES <= _tables(db)


def test_initialise_twice_is_harmless(db):
    with db.connection() as conn:
        conn.execute(USER_SQL, ("keep.me", "EMPLOYEE"))
    db.initialise()                                       # second run must not fail or wipe data
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_initialise_creates_missing_parent_folder(tmp_path):
    database = Database(tmp_path / "data" / "nested" / "iitsm.db")
    database.initialise()
    assert EXPECTED_TABLES <= _tables(database)


def test_wal_mode_is_switched_on(db):
    with db.connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_foreign_keys_are_enforced_on_every_connection(db):
    with db.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(PersistenceError) as caught:
        with db.connection() as conn:                     # no user with id 1 exists yet
            conn.execute("INSERT INTO categories (name, required_skill) VALUES ('c', 's')")
            conn.execute("INSERT INTO it_services (name, business_criticality) VALUES ('s', 1)")
            conn.execute(INCIDENT_SQL, ("INC-1001",))
    assert "FOREIGN KEY" in caught.value.message


def test_rows_are_readable_by_column_name(db):
    with db.connection() as conn:
        conn.execute(USER_SQL, ("alice", "EMPLOYEE"))
        row = conn.execute("SELECT username, role FROM users").fetchone()
    assert (row["username"], row["role"]) == ("alice", "EMPLOYEE")


# ---- constraints the schema must enforce ------------------------------------------

def test_duplicate_username_raises_persistence_error_with_clear_message(db):
    with db.connection() as conn:
        conn.execute(USER_SQL, ("dup", "EMPLOYEE"))
    with pytest.raises(PersistenceError) as caught:
        with db.connection() as conn:
            conn.execute(USER_SQL, ("dup", "TECHNICIAN"))
    assert "users.username" in caught.value.message


def test_unknown_role_is_rejected(db):
    with pytest.raises(PersistenceError):
        with db.connection() as conn:
            conn.execute(USER_SQL, ("x", "SUPERUSER"))


def test_ticket_number_must_be_unique(db):
    with db.connection() as conn:
        _seed_incident_prerequisites(conn)
        conn.execute(INCIDENT_SQL, ("INC-1001",))
    with pytest.raises(PersistenceError):
        with db.connection() as conn:
            conn.execute(INCIDENT_SQL, ("INC-1001",))


def test_sla_event_cannot_be_recorded_twice_for_one_incident(db):
    with db.connection() as conn:
        _seed_incident_prerequisites(conn)
        conn.execute(INCIDENT_SQL, ("INC-1001",))
        conn.execute("INSERT INTO sla_events (incident_id, event_type, recorded_at) "
                     "VALUES (1, 'RESPONSE_WARNING', '2026-11-14 10:30:00')")
    with pytest.raises(PersistenceError):
        with db.connection() as conn:
            conn.execute("INSERT INTO sla_events (incident_id, event_type, recorded_at) "
                         "VALUES (1, 'RESPONSE_WARNING', '2026-11-14 10:31:00')")


def test_business_criticality_must_be_between_one_and_three(db):
    with pytest.raises(PersistenceError):
        with db.connection() as conn:
            conn.execute("INSERT INTO it_services (name, business_criticality) VALUES ('bad', 4)")


# ---- transaction behaviour --------------------------------------------------------

def test_changes_are_committed_when_the_block_ends_normally(db):
    with db.connection() as conn:
        conn.execute(USER_SQL, ("committed", "EMPLOYEE"))
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_changes_are_rolled_back_when_an_error_occurs(db):
    with pytest.raises(PersistenceError):
        with db.connection() as conn:
            conn.execute(USER_SQL, ("half.done", "EMPLOYEE"))
            conn.execute("THIS IS NOT SQL")
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_own_exceptions_pass_through_and_still_roll_back(db):
    with pytest.raises(NotFoundError):
        with db.connection() as conn:
            conn.execute(USER_SQL, ("rolled.back", "EMPLOYEE"))
            raise NotFoundError("nothing here")
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_bad_statement_raises_persistence_error_not_a_raw_sqlite_error(db):
    with pytest.raises(PersistenceError) as caught:
        with db.connection() as conn:
            conn.execute("SELECT * FROM table_that_does_not_exist")
    assert not isinstance(caught.value, sqlite3.Error)
    assert isinstance(caught.value.__cause__, sqlite3.Error)   # original kept for debugging


# ---- unusable paths ---------------------------------------------------------------

def test_path_inside_a_file_surfaces_as_persistence_error(tmp_path):
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("i am a file, not a folder")
    with pytest.raises(PersistenceError):
        Database(blocker / "iitsm.db").initialise()


def test_path_that_is_a_folder_surfaces_as_persistence_error(tmp_path):
    with pytest.raises(PersistenceError):
        with Database(tmp_path).connection() as conn:
            conn.execute("SELECT 1")


@pytest.mark.parametrize("name", [":memory:", "", "  "])
def test_in_memory_database_is_refused_with_an_explanation(name):
    with pytest.raises(PersistenceError) as caught:
        Database(name)
    assert "file path" in caught.value.message
