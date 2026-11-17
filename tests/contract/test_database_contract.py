"""Contract: the code, the Python contracts and the real database schema agree.

Needs the local Supabase (`supabase start`). Every check scans the code as it is, so adding a
query, an RPC call, a table or a vocabulary word that disagrees with the migrations fails
here, not in front of a teacher.

Read top to bottom it follows one run of the application against the database: what each
component may read and call, what it may store, who may write, and the words every component
must agree on (event types, statuses, evidence, supports).
"""

import json
import re
from collections import defaultdict
from typing import get_args, get_type_hints

import pytest

from shared.contracts import (
    Activity,
    Event,
    EventType,
    EvidenceSource,
    InterventionKey,
    SeatState,
    Session,
    SessionSummary,
)
from tests.contract import scan
from tests.support import local_supabase as db

pytestmark = pytest.mark.contract

# Who makes the call. The dashboard in the browser is the signed-in teacher; vision, the agent
# and the dashboard's own server routes use the backend key.
SERVER_FILES = {
    "web/lib/photon-registration.ts",
    "web/lib/notification-send.ts",
    "web/lib/notification-test.ts",
}
SERVER_DIRS = ("agent/", "vision/", "shared/", "web/app/api/")


def caller_role(path: str) -> str:
    server = path in SERVER_FILES or path.startswith(SERVER_DIRS)
    return "service_role" if server else "authenticated"


@pytest.fixture(scope="module")
def columns(supabase_stack):
    found: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in db.sql(
        "select table_name, column_name, is_nullable, column_default "
        "from information_schema.columns where table_schema = 'public'"
    ):
        found[row["table_name"]][row["column_name"]] = row
    return found


@pytest.fixture(scope="module")
def functions(supabase_stack):
    """function name -> list of overloads, each a dict of argument name -> has a default."""
    found: dict[str, list[dict[str, bool]]] = defaultdict(list)
    rows = db.sql(
        "select proname, pg_get_function_arguments(oid) as args from pg_proc "
        "where pronamespace = 'public'::regnamespace"
    )
    for row in rows:
        args: dict[str, bool] = {}
        for part in filter(None, (a.strip() for a in row["args"].split(","))):
            name = part.split()[0]
            args[name] = " default " in part.lower()
        found[row["proname"]].append(args)
    return found


def check_definitions(table: str) -> list[str]:
    return [
        row["definition"]
        for row in db.sql(
            "select pg_get_constraintdef(oid) as definition from pg_constraint "
            f"where conrelid = 'public.{table}'::regclass and contype = 'c'"
        )
    ]


def quoted_words(text: str) -> set[str]:
    return set(re.findall(r"'([a-z_]+)'::text", text))


# ---- 1. Everything the code reads, calls and stores exists ---------------------------------


def test_the_scanner_actually_finds_calls(columns, functions):
    """Guard: a scanner that finds nothing would make every test below pass for no reason."""
    assert len(scan.table_uses()) >= 20
    assert len(scan.rpc_uses(set(functions))) >= 10


def test_every_column_the_code_selects_or_filters_exists(columns):
    problems = []
    for use in scan.table_uses():
        if use.table not in columns:
            problems.append(f"{use.file}:{use.line} table {use.table!r} does not exist")
            continue
        missing = sorted(use.columns - set(columns[use.table]))
        if missing:
            problems.append(f"{use.file}:{use.line} {use.table} has no column(s) {missing}")
    assert not problems, "\n".join(problems)


def test_every_rpc_call_matches_a_database_function(columns, functions):
    problems = []
    for use in scan.rpc_uses(set(functions)):
        if not use.functions:
            problems.append(f"{use.file}:{use.line} calls a function the database does not have")
            continue
        overloads = [o for name in use.functions for o in functions[name]]
        accepted = {arg for o in overloads for arg in o}
        unknown = sorted(use.keys - accepted)
        if unknown:
            problems.append(f"{use.file}:{use.line} passes unknown argument(s) {unknown}")
        for name in use.functions:
            # At least one overload must be satisfiable: all its required arguments are passed.
            if not any(
                all(has_default or arg in use.keys for arg, has_default in o.items())
                for o in functions[name]
            ):
                problems.append(f"{use.file}:{use.line} {name} is missing a required argument")
    assert not problems, "\n".join(problems)


def test_every_caller_may_execute_the_functions_it_calls(functions):
    """The browser calls only what a signed-in teacher may run, the backend what it may run."""
    problems = []
    for use in scan.rpc_uses(set(functions)):
        role = caller_role(use.file)
        for name in use.functions:
            allowed = db.sql(
                "select bool_or(has_function_privilege("
                f"'{role}', p.oid, 'execute')) as ok from pg_proc p "
                f"where p.pronamespace = 'public'::regnamespace and p.proname = '{name}'"
            )[0]["ok"]
            if not allowed:
                problems.append(f"{use.file}:{use.line} calls {name} as {role}, which may not")
    assert not problems, "\n".join(problems)


def test_every_caller_may_read_the_tables_it_selects_from(columns):
    problems = []
    for use in scan.table_uses():
        role = caller_role(use.file)
        if use.table not in columns or role == "service_role":
            continue
        allowed = db.sql(
            f"select has_table_privilege('{role}', 'public.{use.table}', 'select') as ok"
        )[0]["ok"]
        if not allowed:
            problems.append(f"{use.file}:{use.line} reads {use.table} as {role}, which may not")
    assert not problems, "\n".join(problems)


def test_the_tables_the_dashboard_follows_live_are_published_to_realtime(columns):
    followed: set[str] = set()
    for path in scan.source_files():
        if path.suffix in {".ts", ".tsx"}:
            followed.update(re.findall(r"schema: \"public\",\s*table: \"(\w+)\"", path.read_text()))
    assert {"seat_state", "teacher_reviews", "sessions", "station_runtime"} <= followed
    published = {
        row["tablename"]
        for row in db.sql(
            "select tablename from pg_publication_tables "
            "where pubname = 'supabase_realtime' and schemaname = 'public'"
        )
    }
    assert followed <= published, f"not in the realtime publication: {sorted(followed - published)}"


# ---- 2. What each component stores fits the table it is stored in --------------------------


@pytest.mark.parametrize(
    ("model", "table"),
    [
        (Event, "events"),
        (SeatState, "seat_state"),
        (Session, "sessions"),
        (Activity, "activities"),
        (SessionSummary, "session_summaries"),
    ],
)
def test_python_contract_fields_are_columns_and_required_columns_are_fields(columns, model, table):
    table_columns = columns[table]
    extra = sorted(set(model.model_fields) - set(table_columns))
    assert not extra, f"{model.__name__} has fields {extra} that {table} does not store"
    required = [
        name
        for name, col in table_columns.items()
        if col["is_nullable"] == "NO" and col["column_default"] is None
    ]
    missing = sorted(set(required) - set(model.model_fields))
    assert not missing, f"{table} requires {missing} but {model.__name__} never provides them"


def test_shared_fixtures_load_into_their_tables_with_matching_types(supabase_stack):
    """jsonb_populate_record raises when a value does not fit the column's type."""
    from tests.contract.fixtures import fixture_rows

    for table, rows in {
        "events": fixture_rows("events.json", Event),
        "seat_state": fixture_rows("seat_states.json", SeatState),
        "activities": fixture_rows("activities.json", Activity),
    }.items():
        for row in rows:
            literal = json.dumps(row).replace("'", "''")
            db.sql(f"select * from jsonb_populate_record(null::public.{table}, '{literal}'::jsonb)")


def test_the_activities_vision_can_run_exist_in_the_database(supabase_stack):
    """A teacher can start a task only if the database has it: built-in tasks must be there."""
    from vision.activities import load_activities

    stored = {row["id"]: row for row in db.sql("select * from public.activities")}
    builtin = {a.id: a for a in load_activities().values() if a.builtin or a.id == "raise_hand"}
    assert set(builtin) <= set(stored), sorted(set(builtin) - set(stored))
    for activity_id, activity in builtin.items():
        row = stored[activity_id]
        assert row["check_type"] == activity.check_type, activity_id
        if activity.check_type == "gesture":
            assert row["success_threshold"] == pytest.approx(activity.success_threshold)
            assert row["review_threshold"] == pytest.approx(activity.review_threshold)


# ---- 3. The words every component must share -----------------------------------------------


def test_the_event_types_the_database_guards_are_the_ones_vision_produces(supabase_stack):
    """The guard that rejects stale observations lists the event types by name: an event type
    vision adds that the guard does not list would slip past it."""
    from tests.support.vision_harness import scripted_run, whole_class

    emitter, _ = scripted_run(whole_class())
    produced = {event.type.value for event in emitter.events}
    source = db.function_source("guard_managed_observation")
    match = re.search(r"NEW\.type not in \(([^)]*)\)", source)
    assert match, "the observation guard no longer lists event types"
    guarded = set(re.findall(r"'(\w+)'", match.group(1)))
    assert guarded == produced
    assert produced <= {t.value for t in EventType}


def test_review_statuses_are_the_same_in_python_and_the_database(supabase_stack):
    from agent.teacher_review import TeacherReview

    python = set(get_args(TeacherReview.model_fields["status"].annotation))
    stored = set()
    for definition in check_definitions("teacher_reviews"):
        if "ANY (ARRAY['pending'" in definition:
            stored |= quoted_words(definition)
    assert python == {"pending", "confirmed", "dismissed", "expired", "reviewed"}
    assert stored == python


def test_evidence_labels_are_the_same_in_python_and_the_database(supabase_stack):
    stored: set[str] = set()
    for definition in check_definitions("teacher_reviews"):
        match = re.search(r"<@ '(\[[^']*\])'::jsonb", definition)
        if match:
            stored = set(json.loads(match.group(1)))
    assert stored == set(get_args(EvidenceSource))


def test_review_priorities_are_the_same_in_python_and_the_database(supabase_stack):
    from agent.escalation import EscalationDecision

    hints = get_type_hints(EscalationDecision)["priority"]
    python = {value for part in get_args(hints) for value in get_args(part)}
    stored: set[str] = set()
    for definition in check_definitions("teacher_reviews"):
        if "priority = ANY" in definition:
            stored = quoted_words(definition)
    assert python == stored == {"normal", "elevated"}


def test_the_approved_support_menu_is_the_same_everywhere_it_is_enforced(supabase_stack):
    """The agent may suggest, and the teacher approve, only these keys: the Python menu, the
    review and approval constraints and the approval function must list exactly them."""
    from shared.contracts import INTERVENTION_MENU

    menu = set(INTERVENTION_MENU)
    assert menu == set(get_args(InterventionKey))
    on_reviews: set[str] = set()
    for definition in check_definitions("teacher_reviews"):
        if "suggested_intervention" in definition:
            on_reviews = quoted_words(definition)
    on_approvals: set[str] = set()
    for definition in check_definitions("interventions"):
        if "action" in definition:
            on_approvals = quoted_words(definition)
    in_function = re.search(
        r"chosen not in \(([^)]*)\)", db.function_source("approve_review_intervention")
    )
    assert in_function, "approve_review_intervention no longer checks the menu"
    assert on_reviews == on_approvals == menu
    assert set(re.findall(r"'(\w+)'", in_function.group(1))) == menu


def test_progress_trends_are_the_same_in_python_and_the_database(supabase_stack):
    from agent.progress import ProgressState

    python = set(get_args(get_type_hints(ProgressState)["trend"]))
    source = db.function_source("publish_task_progress")
    match = re.search(r"p_progress->>'trend' not in \(([^)]*)\)", source)
    assert match, "publish_task_progress no longer checks the trend"
    assert set(re.findall(r"'(\w+)'", match.group(1))) == python


def test_station_runtime_statuses_are_the_ones_the_dashboard_accepts(supabase_stack):
    from tests.support.typescript import run_parser

    stored: set[str] = set()
    for definition in check_definitions("station_runtime"):
        if "'ready'" in definition:
            stored = quoted_words(definition)
    assert stored == {"ready", "idle", "error"}
    for status in stored:
        runtime = {
            "station_id": "S1",
            "session_id": None,
            "activity_id": None,
            "revision": None,
            "status": status,
            "error": None,
            "updated_at": "2026-11-14T00:00:00+00:00",
            "agent_seen_at": None,
        }
        assert run_parser("runtime", {"station_runtime": runtime}, "S1")["status"] == status


# ---- 4. Who may write, who may read ---------------------------------------------------------


def test_every_table_has_row_level_security(columns):
    rows = db.sql(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind in ('r', 'p')"
    )
    assert len(rows) >= 15, "the schema lookup found too few tables"
    unprotected = sorted(row["relname"] for row in rows if not row["relrowsecurity"])
    assert not unprotected, f"row level security is off for {unprotected}"


def test_browsers_write_nothing_except_the_teachers_own_profile(columns):
    """No browser table writes: sessions, reviews, approvals and state change only through
    RPCs that check who the teacher is. The one exception is the profile row."""
    rows = db.sql(
        "select t.relname as tbl, r.rolname as role, p.priv as priv "
        "from pg_class t "
        "cross join (values ('anon'), ('authenticated')) r(rolname) "
        "cross join (values ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE')) p(priv) "
        "where t.relnamespace = 'public'::regnamespace and t.relkind = 'r' "
        "and has_table_privilege(r.rolname, t.oid, p.priv)"
    )
    granted = {(row["tbl"], row["role"], row["priv"]) for row in rows}
    assert granted == {
        ("teacher_profiles", "authenticated", "INSERT"),
        ("teacher_profiles", "authenticated", "UPDATE"),
    }


def test_signed_out_visitors_read_only_the_simulated_demo_tables(columns):
    rows = db.sql(
        "select t.relname as tbl from pg_class t "
        "where t.relnamespace = 'public'::regnamespace and t.relkind = 'r' "
        "and has_table_privilege('anon', t.oid, 'select')"
    )
    assert {row["tbl"] for row in rows} <= {
        "activities",
        "stations",
        "seats",
        "sessions",
        "seat_state",
    }


# Functions only the backend (vision, the agent, the dashboard's server routes) may run.
BACKEND_ONLY = [
    "station_tick",
    "station_snapshot",
    "report_station_session",
    "publish_task_progress",
    "claim_station_writer",
    "release_station_writer",
    "issue_station_pairing_code",
    "prepare_teacher_notification_registration",
    "record_teacher_notification_send",
    "summarize_session",
    "prune_old_events",
]
# Functions a signed-in teacher runs from the dashboard. Each checks who the teacher is.
TEACHER_ONLY = [
    "get_or_create_my_default_station",
    "redeem_station_pairing_code",
    "read_station_session",
    "start_station_activity",
    "end_station_session",
    "mark_seat_reviewed",
    "approve_review_intervention",
    "resolve_teacher_review",
    "read_station_flags",
    "teacher_insights",
]


@pytest.mark.parametrize("name", BACKEND_ONLY)
def test_backend_functions_are_not_callable_from_a_browser(supabase_stack, name):
    assert not any(db.may_execute("anon", name)), f"a signed-out visitor may run {name}"
    assert not any(db.may_execute("authenticated", name)), f"a teacher's browser may run {name}"
    assert all(db.may_execute("service_role", name)), f"the backend cannot run {name}"


@pytest.mark.parametrize("name", TEACHER_ONLY)
def test_teacher_functions_need_a_signed_in_teacher(supabase_stack, name):
    assert not any(db.may_execute("anon", name)), f"a signed-out visitor may run {name}"
    assert all(db.may_execute("authenticated", name)), f"a teacher cannot run {name}"


# ---- 5. What the code reads back is a column it stores ---------------------------------------


def test_agent_seat_state_read_columns_are_contract_fields(columns):
    """The agent reads these columns and validates them as SeatState: each must be both."""
    from agent.seat_state_runtime import SupabaseSeatStateSource

    fields = {f.strip() for f in SupabaseSeatStateSource.FIELDS.split(",")}
    assert fields <= set(columns["seat_state"]), fields - set(columns["seat_state"])
    assert fields == set(SeatState.model_fields)
