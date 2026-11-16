"""Contract: what the code reads, writes and calls matches the real database schema.

Needs the local Supabase (`supabase start`). Every check scans the code as it is, so adding a
query or RPC call that disagrees with the migrations fails here, not in front of a teacher.
"""

import json
import re
from collections import defaultdict

import pytest

from shared.contracts import Activity, Event, SeatState, Session
from tests.contract import scan
from tests.support import local_supabase as db

pytestmark = pytest.mark.contract


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


@pytest.mark.parametrize(
    ("model", "table"),
    [(Event, "events"), (SeatState, "seat_state"), (Session, "sessions"), (Activity, "activities")],
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


def test_agent_seat_state_read_columns_are_contract_fields(columns):
    """The agent reads these columns and validates them as SeatState: each must be both."""
    from agent.seat_state_runtime import SupabaseSeatStateSource

    fields = {f.strip() for f in SupabaseSeatStateSource.FIELDS.split(",")}
    assert fields <= set(columns["seat_state"]), fields - set(columns["seat_state"])
    assert fields <= set(SeatState.model_fields), fields - set(SeatState.model_fields)


def test_review_rows_the_agent_writes_fit_the_teacher_reviews_table(columns):
    from datetime import UTC, datetime
    from uuid import UUID

    from agent.assessment import AgentAssessment
    from agent.escalation import EscalationDecision
    from agent.progress import ProgressState
    from agent.router import AgentEvaluationRequest
    from agent.supabase_teacher_review import review_to_row
    from agent.teacher_review import TeacherReviewStore

    now = datetime(2026, 11, 14, tzinfo=UTC)
    review = TeacherReviewStore(clock=lambda: now).request_teacher_review(
        AgentEvaluationRequest(
            UUID(int=1),
            "S1-P1",
            "thumbs_up",
            now,
            ProgressState("stalled", 10),
            EscalationDecision(True, "normal", "stalled_progress"),
        ),
        AgentAssessment(
            decision="teacher_review_warranted",
            rationale="Stalled.",
            evidence_used=["current_progress"],
        ),
    )
    row = review_to_row(review)
    unknown = sorted(set(row) - set(columns["teacher_reviews"]))
    assert not unknown, f"the agent writes {unknown}, which teacher_reviews does not have"
    required = {
        name
        for name, col in columns["teacher_reviews"].items()
        if col["is_nullable"] == "NO" and col["column_default"] is None
    }
    assert required <= set(row), f"teacher_reviews requires {sorted(required - set(row))}"
    assert re.fullmatch(r"[0-9a-f-]{36}", str(row.get("id", review.id)))
