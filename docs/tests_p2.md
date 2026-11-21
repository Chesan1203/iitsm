# P2 test cases: database, persistence, seed data, search and reports

The persistence layer has **98 automated tests** in `tests/persistence/`. Run them with
`pytest tests/persistence`. The table below documents 15 of them, covering five of the six required
categories. Every test uses a throwaway database file (pytest's `tmp_path`), never the real one.

**Authorization** is not tested here on purpose: the persistence layer only saves and loads, and
deciding who may see or change what is the services layer's job (P3's authorization tests).

Result of the last run: all 98 passed (full project: 815 passed).

| ID | Module | Category | Input or steps | Expected | Actual | Pass? |
| --- | --- | --- | --- | --- | --- | --- |
| DB1 | Incident repository | Normal | Walk an incident from NEW to CLOSED (notes, an information request and answer, resolution, feedback, SLA tracker), save it, load it by id | The loaded incident equals the original, field for field | Equal; notes, resolution, feedback and tracker all present | Pass |
| DB2 | User repository | Invalid input | Save a second user whose username already exists | `PersistenceError` that mentions the username; the object gets no id | Raised with `users.username` in the message; `id` stayed `None` | Pass |
| DB3 | Incident repository (search) | Normal | Search with status CLASSIFIED and priority P1 | Only the incident matching both is returned | One incident returned; the status NEW plus P1 search returned none | Pass |
| DB4 | Incident repository (search) | Boundary | Search with no criteria; then with a keyword nothing contains | Everything, newest first; then an empty list | All three incidents newest first; empty list | Pass |
| DB5 | Report repository | Business rule | Technician workload with one busy technician, one with no incidents, and a CLOSED incident | Both technicians listed; the closed incident is not counted as active | Busy one 2, idle one 0; employees and admins not listed | Pass |
| DB6 | Incident repository (search) | Invalid input | Search with keyword `x' OR '1'='1` and ticket `' OR 1=1 --` | Treated as plain text: no matches, and no data harmed | No matches; the incidents table still had all 3 rows | Pass |
| DB7 | Database helper | Exception | Open a database whose path lies inside a regular file | `PersistenceError`, not a raw `sqlite3` error | `PersistenceError` raised | Pass |
| DB8 | SLA event repository | Business rule | Save the same (incident, event type) pair twice | The second save raises `PersistenceError`; only one row exists | Raised; one row stored | Pass |
| DB9 | Incident repository (search) | Boundary | Search with the from date and to date set to the same day | Incidents created any time on that day are included, later days are not | Both 14 Nov incidents returned, the 17 Nov one excluded | Pass |
| DB10 | Database helper | Exception | Insert a user, then run an invalid statement in the same block | The whole block is rolled back; no user is stored | `PersistenceError`; the users table was empty afterwards | Pass |
| DB11 | Incident repository | Business rule | Save two new incidents | Tickets `INC-1001` then `INC-1002`, ids 1 then 2 | Matched | Pass |
| DB12 | Report repository | Business rule | Six incidents (NEW, two open P1, one P4, one CLOSED P1, one RESOLVED) with violation events on one incident | total 6, open 4, critical open 2, resolved 2, SLA violations 1 (two events on one incident count once, warnings ignored) | Matched | Pass |
| DB13 | Seeder | Business rule | Seed an empty database; compare the three payment titles with the duplicate detector | Each flags the other two as possible duplicates; the first has no duplicate marker, the others point to it | Matched | Pass |
| DB14 | Incident repository | Exception | Save an incident whose reporter was never saved | `PersistenceError`; the incident gets no id or ticket number and no row is written | Matched | Pass |
| DB15 | Incident repository (search) | Boundary | Keywords `100%` against titles "Disk at 100% full" and "Disk at 100 full" | `%` is a literal character, so only the first matches | Only "Disk at 100% full" returned | Pass |

## Where each ID lives

| ID | Test function | File |
| --- | --- | --- |
| DB1 | `test_full_lifecycle_incident_round_trips_with_notes_resolution_feedback_and_tracker` | `test_incident_repository.py` |
| DB2 | `test_duplicate_username_raises_and_leaves_no_id` | `test_simple_repositories.py` |
| DB3 | `test_search_status_and_priority_narrow_together` | `test_incident_repository.py` |
| DB4 | `test_search_with_no_criteria_returns_everything_newest_first`, `test_search_keyword_matches_title_or_description_ignoring_case` | `test_incident_repository.py` |
| DB5 | `test_workload_includes_technicians_with_zero_and_excludes_closed_incidents` | `test_report_repository.py` |
| DB6 | `test_search_treats_sql_injection_text_as_plain_text` | `test_incident_repository.py` |
| DB7 | `test_path_inside_a_file_surfaces_as_persistence_error` | `test_database.py` |
| DB8 | `test_same_sla_event_twice_raises_persistence_error` | `test_records_repositories.py` |
| DB9 | `test_search_date_range_includes_the_whole_end_day` | `test_incident_repository.py` |
| DB10 | `test_changes_are_rolled_back_when_an_error_occurs` | `test_database.py` |
| DB11 | `test_first_save_assigns_id_and_ticket_numbers_in_sequence` | `test_incident_repository.py` |
| DB12 | `test_overview_counts_open_critical_resolved_and_violations` | `test_report_repository.py` |
| DB13 | `test_three_payment_sentences_flag_each_other_as_duplicates` | `test_seeder.py` |
| DB14 | `test_saving_with_an_unsaved_reporter_fails_and_assigns_no_identity` | `test_incident_repository.py` |
| DB15 | `test_search_percent_and_underscore_are_literal_characters` | `test_incident_repository.py` |

## What the other tests cover

- **`test_database.py` (20):** schema creation, running it twice, WAL mode, foreign keys, every
  constraint (unique names, valid roles, criticality range), commit and rollback.
- **`test_simple_repositories.py` (22):** settings, categories, services, SLA policies and users:
  save, update, round trip, lookups and rejected input.
- **`test_incident_repository.py` (19):** saving, loading, all search criteria, helper queries,
  and a check that loading a list needs only a handful of queries.
- **`test_records_repositories.py` (8):** audit records, notifications and SLA events.
- **`test_report_repository.py` (7):** the five report queries.
- **`test_seeder.py` (22):** the demo data: counts, idempotency, consistency with the live SLA,
  duplicate, correlation and escalation engines, audit trails and notifications.
