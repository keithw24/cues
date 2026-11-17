"""Contract: the product's non-negotiables hold across every component, for a whole run.

Privacy, no biometric identification, expression as supporting context only, the teacher's
approval before anything changes, and a minimal text message. Each rule is checked where it
could be broken: in the schema, in the shared contracts, in the code that moves data, and in
the files that are committed. These are the checks that must fail loudly if a change quietly
weakens a promise the product makes to a teacher or a family.
"""

import re
import subprocess
from pathlib import Path

import pytest

from shared.contracts import (
    Activity,
    Event,
    ExpressionContext,
    InsightsSummary,
    SeatState,
    Session,
    SessionSummary,
)
from tests.contract import scan
from tests.support import local_supabase as db

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    return result.returncode == 0


# ---- Camera frames and raw camera data never leave the laptop ------------------------------------


CAMERA_WORDS = re.compile(
    r"(?:^|_)(?:images?|frames?|photos?|video|jpe?g|png|pixels?|landmarks?|embeddings?"
    r"|biometrics?|faces?|crops?|blob)(?:_|$)"
)


def test_no_table_can_hold_a_picture_or_raw_camera_data(supabase_stack):
    columns = db.sql(
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = 'public'"
    )
    assert len(columns) > 100, "the schema lookup found too few columns"
    problems = [
        f"{c['table_name']}.{c['column_name']} ({c['data_type']})"
        for c in columns
        if c["data_type"] in ("bytea", "oid", "USER-DEFINED", "tsvector")
        or CAMERA_WORDS.search(c["column_name"])
    ]
    assert not problems, f"columns that could hold camera data: {problems}"


def test_the_shared_contracts_carry_no_identity_and_no_camera_data():
    forbidden = re.compile(r"name|student|child|face|embedding|image|frame|photo|landmark|email")
    for model in (Event, SeatState, Session, Activity, ExpressionContext):
        fields = set(model.model_fields)
        offenders = {f for f in fields if forbidden.search(f) and f != "name"}
        assert not offenders, f"{model.__name__} carries {sorted(offenders)}"
    # Even the long-term summaries name no seat, child or time of a particular person.
    for model in (SessionSummary, InsightsSummary):
        assert not {f for f in model.model_fields if re.search(r"seat|child|student", f)}


def test_gesture_examples_stay_on_the_laptop():
    """Recorded gestures live in vision/templates/, git-ignored, and no code that talks to the
    network (the database writer, the session sync, the agent, the dashboard) touches them."""
    for name in ("vision/templates/wave.json", "vision/templates/custom_gestures.catalog.json"):
        assert ignored(name), f"{name} is not git-ignored"
    assert git("ls-files", "vision/templates").strip() == "", "gesture examples are committed"
    networked = [
        "vision/events.py",
        "vision/session_sync.py",
        "vision/station_lease.py",
        "vision/supabase_client.py",
        "vision/review_marks.py",
    ]
    for relative in networked:
        assert "templates" not in (ROOT / relative).read_text().lower(), relative
    for path in scan.source_files():
        relative = str(path.relative_to(ROOT))
        if relative.startswith(("agent/", "shared/", "web/")):
            text = path.read_text()
            assert "vision/templates" not in text and "custom_gestures" not in text, relative


# ---- Who writes what: the teacher decides, the backend never changes a task -----------------


def writers_of_tables() -> dict[str, set[str]]:
    """Which source files insert, update or delete rows of which table (static scan)."""
    found: dict[str, set[str]] = {}
    pattern = re.compile(r"""\b(?:from|table)\(\s*["'](\w+)["']\s*\)""")
    for path in scan.source_files():
        text = path.read_text()
        for match in pattern.finditer(text):
            chain = text[match.end() : match.end() + 500]
            chain = chain[: chain.find(".execute()")] if ".execute()" in chain else chain
            if re.search(r"\.(insert|upsert|update|delete)\(", chain):
                found.setdefault(match.group(1), set()).add(str(path.relative_to(ROOT)))
    return found


def test_only_the_expected_components_write_the_expected_tables():
    """Nothing writes a student's task, a support approval, a mark or a session directly: those
    change only through a teacher's signed-in RPC. The writes that exist are these."""
    assert writers_of_tables() == {
        "events": {"vision/events.py"},
        "seat_state": {"vision/events.py"},
        "teacher_reviews": {"agent/supabase_teacher_review.py"},
        "teacher_profiles": {"web/lib/teacher-profile.ts"},
    }


def test_one_open_review_per_person_so_a_teacher_is_not_asked_twice(supabase_stack):
    indexes = db.sql(
        "select indexdef from pg_indexes where schemaname = 'public' "
        "and tablename = 'teacher_reviews'"
    )
    unique = [i["indexdef"] for i in indexes if "UNIQUE" in i["indexdef"]]
    assert any(
        "session_id, seat_id, activity_id" in d and "status = 'pending'" in d for d in unique
    ), unique
    one_approval = db.sql(
        "select indexdef from pg_indexes where schemaname = 'public' "
        "and tablename = 'interventions' and indexdef like '%UNIQUE%'"
    )
    assert any("review_id" in i["indexdef"] for i in one_approval)


# ---- Expression is supporting evidence only ------------------------------------------------------


def test_expression_is_stored_only_as_the_latest_context_and_as_sustained_events(supabase_stack):
    holders = db.sql(
        "select table_name, column_name from information_schema.columns "
        "where table_schema = 'public' and column_name ilike '%expression%'"
    )
    assert {(h["table_name"], h["column_name"]) for h in holders} == {
        ("seat_state", "expression_context")
    }, "a new place stores expression: it must not become a history"
    primary = db.sql(
        "select a.attname from pg_index i join pg_attribute a on a.attrelid = i.indrelid "
        "and a.attnum = any(i.indkey) where i.indrelid = 'public.seat_state'::regclass "
        "and i.indisprimary"
    )
    assert [p["attname"] for p in primary] == ["seat_id"], "seat_state must keep one row per seat"


def test_an_expression_context_is_always_labelled_supporting_only():
    with pytest.raises(ValueError):
        ExpressionContext(label="sadness", probability=0.7, supporting_only=False)
    with pytest.raises(ValueError):
        ExpressionContext(label="sad", probability=0.7)
    with pytest.raises(ValueError, match="duration_seconds"):
        Event(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            station_id="S1",
            seat_id="S1-P1",
            type="expression_context",
            created_at="2026-11-14T09:00:00Z",
            payload={"label": "sadness", "probability": 0.7, "supporting_only": True},
        )


# ---- Secrets and the browser ------------------------------------------------------------------


def web_sources(suffixes: set[str]):
    """The dashboard's own source files (not its installed packages)."""
    for folder in ("app", "components", "lib"):
        for path in (ROOT / "web" / folder).rglob("*"):
            if path.is_file() and path.suffix in suffixes:
                yield path
    for path in (ROOT / "web").glob("*"):
        if path.is_file() and path.suffix in suffixes:
            yield path


def test_browser_visible_settings_hold_only_the_public_supabase_pair():
    allowed = {"NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"}
    seen: set[str] = set()
    for path in web_sources({".ts", ".tsx", ".mjs", ".js"}):
        seen |= set(re.findall(r"NEXT_PUBLIC_\w+", path.read_text()))
    example = (ROOT / ".env.example").read_text()
    seen |= set(re.findall(r"^(NEXT_PUBLIC_\w+)=", example, re.M))
    assert seen == allowed, f"browser-visible settings: {sorted(seen)}"
    for name in allowed:
        assert re.search(rf"^{name}=\s*$", example, re.M), f"{name} has a real value in the example"


def test_secrets_are_read_only_by_server_code():
    server = {
        "web/app/api/notifications/register/route.ts",
        "web/app/api/notifications/test/route.ts",
    }
    secret = re.compile(r"SERVICE_ROLE|SPECTRUM_PROJECT_SECRET|GROQ_API_KEY")
    users: set[str] = set()
    for path in web_sources({".ts", ".tsx"}):
        text = path.read_text()
        if secret.search(text):
            users.add(str(path.relative_to(ROOT)))
            assert '"use client"' not in text, f"{path} is client code that names a secret"
    assert users == server


def test_no_secret_is_committed():
    assert git("ls-files", ".env", ".env.local").strip() == ""
    assert ignored(".env") and ignored("web/.env.local")
    patterns = {
        "a Supabase secret key": re.compile(r"sb_secret_[A-Za-z0-9_-]{16,}"),
        "a Groq key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
        "a signed JWT": re.compile(
            r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
        ),
        "a private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    }
    skip_suffixes = {".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2", ".lock", ".svg"}
    problems = []
    for relative in git("ls-files").splitlines():
        path = ROOT / relative
        if path.suffix in skip_suffixes or path.name == "package-lock.json" or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        problems += [f"{relative}: {what}" for what, rx in patterns.items() if rx.search(text)]
    assert not problems, problems


# ---- The agent ---------------------------------------------------------------------------------
