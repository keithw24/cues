"""Contract: every hand-off in one run of the application, in the order it happens.

    teacher signs in -> dashboard tells vision its station -> a session starts -> vision
    follows it and publishes what it sees -> the agent reads that and asks for a review ->
    the teacher is told -> the teacher answers -> the session ends and is summarized

Each section checks one hand-off from both sides: what the producer really makes (run through
the producer's own code, not a hand-written example) against what the consumer, the shared
Python contract and the database schema accept. The end-to-end behaviour is in tests/smoke.
"""

import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from shared.contracts import (
    Event,
    EventType,
    ExpressionLabel,
    SeatState,
    SeatStatus,
    Session,
)
from tests.support import local_supabase as db
from tests.support.typescript import run_parser
from tests.support.vision_harness import (
    SAD,
    ScriptedVision,
    View,
    scripted_run,
    whole_class,
)

pytestmark = pytest.mark.contract

NEGATIVE = {"anger", "fear", "sadness"}


def keys_in(function: str, keys) -> list[str]:
    """The keys the database function names in the JSON it builds that are missing."""
    source = db.function_source(function)
    return sorted(key for key in keys if f"'{key}'" not in source)


@pytest.fixture(scope="module")
def class_run():
    """One minute of a whole class through vision's real status stage."""
    return scripted_run(whole_class())


# ---- 1. The dashboard and the vision service on the teacher's laptop ---------------------------


@pytest.fixture
def local_vision(monkeypatch):
    """Vision's real HTTP service on a fake camera, reached the way the dashboard reaches it."""
    from fastapi.testclient import TestClient

    from vision import station
    from vision.app import create_app
    from vision.camera import FakeCamera
    from vision.pipeline import Pipeline

    monkeypatch.setattr(station, "STATION", station.ActiveStation(None))
    app = create_app(Pipeline(FakeCamera(), []))
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
        yield client


def test_the_dashboard_reads_what_vision_reports_about_the_camera(local_vision):
    health = local_vision.get("/health").json()
    config = local_vision.get("/config").json()
    assert {"camera_open", "frame_age_seconds", "station_id"} <= set(health)
    assert {"station_id", "pinned", "station_busy"} <= set(config)
    reading = run_parser("vision_read", {"health": health, "config": config})["reading"]
    assert reading["reachable"] is True and reading["cameraOpen"] is True
    assert reading["stationId"] is None
    assert reading["pinned"] is False and reading["stationBusy"] is False


def test_the_station_the_dashboard_sends_is_one_vision_accepts(local_vision):
    from vision.routes.station import StationConfig
    from vision.session_sync import WAKE

    answer = {"station_id": "S4", "pinned": False, "station_busy": False, "changed": True}
    sent = run_parser("vision_configure", {"station": "S4", "refresh": True, "response": answer})
    assert sent["result"] == "configured"
    request = sent["sent"][0]
    assert request["method"] == "POST" and request["url"].endswith("/config")
    body = request["body"]
    assert set(body) == {"station_id", "refresh"}
    StationConfig.model_validate(body)
    reply = local_vision.post("/config", json=body)
    WAKE.clear()
    assert reply.status_code == 200
    assert reply.json() == answer | {"station_id": "S4"}

    # The same station again is "unchanged", and then the dashboard sends no refresh flag.
    plain = run_parser("vision_configure", {"station": "S4", "response": {"changed": False}})
    assert plain["result"] == "unchanged"
    assert plain["sent"][0]["body"] == {"station_id": "S4"}
    again = local_vision.post("/config", json=plain["sent"][0]["body"])
    assert again.status_code == 200 and again.json()["changed"] is False

    # Signing out clears the station, so vision stops writing for that teacher.
    signed_out = run_parser("vision_configure", {"station": None, "response": {"changed": True}})
    assert signed_out["sent"][0]["body"] == {"station_id": None}
    cleared = local_vision.post("/config", json={"station_id": None})
    assert cleared.status_code == 200 and cleared.json()["station_id"] is None


def test_vision_accepts_configuration_from_this_laptop_and_the_dashboard_only(local_vision):
    from fastapi.testclient import TestClient

    from vision import station
    from vision.app import create_app
    from vision.camera import FakeCamera
    from vision.pipeline import Pipeline
    from vision.routes.station import _dashboard_origins

    good = {"station_id": "S2"}
    assert local_vision.post("/config", json={"station_id": "bad id"}).status_code == 422
    assert local_vision.post("/config", json={"station_id": 5}).status_code == 422
    assert local_vision.post("/config", json={**good, "extra": 1}).status_code == 422
    foreign_origin = {"origin": "http://evil.example"}
    assert local_vision.post("/config", json=good, headers=foreign_origin).status_code == 403
    foreign_host = {"host": "evil.example"}
    assert local_vision.post("/config", json=good, headers=foreign_host).status_code == 403
    own_origin = {"origin": sorted(_dashboard_origins())[0]}
    assert local_vision.post("/config", json=good, headers=own_origin).status_code == 200
    # Another machine on the network, even with the right headers, is refused.
    app = create_app(Pipeline(FakeCamera(), []))
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("192.168.1.20", 5000)) as far:
        assert far.get("/config").status_code == 403
        assert far.post("/config", json=good).status_code == 403
    # A station pinned for development cannot be changed from the dashboard.
    station.STATION = station.ActiveStation("S1", pinned=True)
    assert local_vision.post("/config", json=good).status_code == 409
    assert local_vision.get("/config").json()["station_id"] == "S1"


# ---- 2. A session starts: what vision reads from the database -----------------------------------


def test_the_session_vision_follows_is_exactly_the_session_contract(supabase_stack):
    missing = keys_in("station_tick", Session.model_fields)
    assert not missing, f"station_tick no longer returns {missing}"
    source = db.function_source("station_tick")
    assert "teacher_id" not in source, "vision must never be told which teacher owns a session"
    # What the lease and the marks need from the same answer.
    assert not keys_in("station_tick", ["granted", "held_seconds_ago", "session", "marks"])
    assert not keys_in("station_tick", ["seat_id", "marked_at"])


def test_a_session_row_is_a_valid_session_and_a_valid_dashboard_session():
    row = {
        "id": str(uuid4()),
        "station_id": "S3",
        "current_activity_id": "thumbs_up",
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": None,
        "revision": 0,
    }
    assert Session.model_validate(row).revision == 0
    owned = row | {"teacher_id": str(uuid4())}  # the dashboard also sees who owns it
    assert run_parser("session", {"session": owned}, "S3")["id"] == row["id"]
    with pytest.raises(ValidationError):
        Session.model_validate(owned)  # vision's contract has no teacher in it
    with pytest.raises(AssertionError, match="rejected"):
        run_parser("session", {"session": row}, "S9")  # another station's session


# ---- 3. Vision publishes: events and seat state ------------------------------------------------


def test_vision_produces_every_event_and_status_it_can(class_run):
    emitter, _ = class_run
    assert {e.type.value for e in emitter.events} == {
        "attempt_success",
        "attempt_miss",
        "review_needed",
        "no_progress",
        "tracking_lost",
        "expression_context",
    }
    assert {s.status for s in emitter.states} == set(SeatStatus)
    # The other event types belong to people and the agent, never to the camera.
    assert not {e.type for e in emitter.events} & {
        EventType.TEACHER_APPROVED,
        EventType.TEACHER_DISMISSED,
        EventType.AGENT_INVOKED,
        EventType.ALERT_CREATED,
    }


def test_everything_vision_writes_round_trips_through_the_shared_contract(class_run):
    emitter, session = class_run
    for event in emitter.events:
        assert Event.model_validate_json(event.model_dump_json()) == event
        assert event.session_id == session.id
        assert event.payload["session_revision"] == session.revision
    for state in emitter.states:
        assert SeatState.model_validate_json(state.model_dump_json()) == state
        assert state.session_id == session.id and state.session_revision == session.revision
        assert state.activity_id == session.current_activity_id


def test_event_payloads_hold_only_the_agreed_scalars(class_run):
    """No landmarks, crops or lists: a payload is a handful of named numbers and words."""
    allowed = {
        "source",
        "session_revision",
        "label",
        "probability",
        "duration_seconds",
        "supporting_only",
    }
    emitter, _ = class_run
    for event in emitter.events:
        assert set(event.payload) <= allowed, event.payload
        assert all(isinstance(v, str | int | float | bool) for v in event.payload.values())


def test_expression_is_supporting_context_published_only_when_sustained(class_run):
    emitter, _ = class_run
    contexts = [s for s in emitter.states if s.expression_context]
    assert contexts and {s.seat_id for s in contexts} == {"S1-P3"}
    for state in contexts:
        context = state.expression_context
        assert context.supporting_only is True
        assert context.label.value in NEGATIVE
        assert context.probability >= 0.5 and context.duration_seconds >= 5.0
    # Nothing is stored as a history: one event for the whole sustained episode.
    expression_events = [e for e in emitter.events if e.type == EventType.EXPRESSION_CONTEXT]
    assert len(expression_events) == 1
    assert expression_events[0].payload["label"] in NEGATIVE
    assert {e.value for e in ExpressionLabel} >= NEGATIVE


def test_expression_alone_never_changes_a_status_or_adds_an_alert():
    """Same child, same scores, with and without a sustained sad-looking expression."""
    calm = ScriptedVision({"S1-P1": View(score=0.1)}).run(40)
    sad = ScriptedVision({"S1-P1": View(score=0.1, expression=SAD)}).run(40)
    assert [s.status for s in sad.emitter.states] == [s.status for s in calm.emitter.states]
    types = {e.type for e in sad.emitter.events} - {EventType.EXPRESSION_CONTEXT}
    assert types == {e.type for e in calm.emitter.events}
    # A child who is succeeding is never flagged because of how they look.
    happy_task = ScriptedVision({"S1-P1": View(score=0.9, expression=SAD)}).run(30)
    assert {e.type for e in happy_task.emitter.events} == {
        EventType.ATTEMPT_SUCCESS,
        EventType.EXPRESSION_CONTEXT,
    }
    statuses = {s.status for s in happy_task.emitter.states}
    assert statuses <= {SeatStatus.IN_PROGRESS, SeatStatus.DONE}


def test_losing_sight_of_a_child_is_a_camera_problem_not_a_failed_attempt():
    run = ScriptedVision({"S1-P1": View(in_view=False, hand=False)}).run(30)
    assert [e.type for e in run.emitter.events] == [EventType.TRACKING_LOST]
    lost = [s for s in run.emitter.states if s.status == SeatStatus.TRACKING_LOST]
    assert lost and all(s.tracking_valid is False and s.task_score is None for s in lost)


def test_the_teachers_mark_sends_a_flagged_child_back_to_working():
    run = ScriptedVision({"S1-P1": View(score=0.1)}).run(10)
    assert run.emitter.states[-1].status == SeatStatus.NEEDS_HELP
    flagged = len([e for e in run.emitter.events if e.type == EventType.NO_PROGRESS])
    run.mark_reviewed("S1-P1")
    run.run(3)
    assert run.emitter.states[-1].status == SeatStatus.IN_PROGRESS
    # A fresh stall is needed before the child is flagged again: not at once.
    assert len([e for e in run.emitter.events if e.type == EventType.NO_PROGRESS]) == flagged


def test_every_row_vision_publishes_is_accepted_by_the_real_tables(supabase_stack, class_run):
    """Insert each shape of event and seat state into the real tables, then undo it all."""
    emitter, _ = class_run
    events = [
        e.model_dump(mode="json") | {"station_id": "CONTRACT"} for e in emitter.events
    ]  # a station that does not exist: the managed-session guard has nothing to compare to
    shapes: dict[tuple, SeatState] = {}
    for state in emitter.states:
        key = (state.status, state.tracking_valid, state.expression_context is not None)
        shapes.setdefault(key, state)
    states = [
        state.model_dump(mode="json") | {"seat_id": f"CONTRACT-P{i}"}
        for i, state in enumerate(shapes.values())
    ]
    assert len(events) >= 6 and len(states) >= 6
    db.insert_and_roll_back("events", events)
    db.insert_and_roll_back("seat_state", states)
    assert not db.sql("select 1 from public.seat_state where seat_id like 'CONTRACT-%'")


def test_every_person_id_vision_can_issue_has_a_seat_row_for_a_new_station(supabase_stack):
    from vision.people import MAX_PEOPLE

    source = db.function_source("get_or_create_my_default_station")
    made = [int(n) for n in re.findall(r"generate_series\(1,\s*(\d+)\)", source)]
    assert made and max(made) >= MAX_PEOPLE
    # Stations that already exist got the extra seats too, not only new ones. (The first four
    # come from older migrations; a freshly seeded S1 has the legacy L/R seats instead.)
    short = db.sql(
        "select s.id from public.stations s where (select count(*) from public.seats "
        "where station_id = s.id and id in (s.id || '-P5', s.id || '-P6')) < 2"
    )
    assert not short, f"stations without the extra person seats: {[r['id'] for r in short]}"


# ---- 4. The agent reads, decides and writes ------------------------------------------------------


def test_the_agent_reads_exactly_what_vision_writes(supabase_stack):
    from agent.seat_state_runtime import SupabaseSeatStateSource

    fields = [f.strip() for f in SupabaseSeatStateSource.FIELDS.split(",")]
    assert not keys_in("station_snapshot", fields)
    assert not keys_in("station_snapshot", ["session", "rows", "marks", "marked_at"])
    assert set(fields) == set(SeatState.model_fields)
    # Camera-derived numbers and a teacher's name are not part of the agent's read.
    assert "evaluated_progress" not in fields and "teacher_id" not in fields


def request_for(reason: str, priority: str, trend: str = "stalled"):
    from agent.escalation import EscalationDecision
    from agent.progress import ProgressState
    from agent.router import AgentEvaluationRequest

    return AgentEvaluationRequest(
        UUID(int=7),
        "S1-P1",
        "thumbs_up",
        datetime(2026, 11, 14, 9, tzinfo=UTC),
        ProgressState(trend, 8.0),
        EscalationDecision(True, priority, reason),
    )


def review_rows(suggestion: str | None = "show_example") -> list[dict]:
    from agent.assessment import AgentAssessment
    from agent.supabase_teacher_review import review_to_row
    from agent.teacher_review import TeacherReviewStore

    rows = []
    for reason, priority in (
        ("stalled_progress", "normal"),
        ("stalled_progress_with_expression_context", "elevated"),
        ("prolonged_stalled_progress", "elevated"),
    ):
        store = TeacherReviewStore(clock=lambda: datetime(2026, 11, 14, 9, 1, tzinfo=UTC))
        review = store.request_teacher_review(
            request_for(reason, priority),
            AgentAssessment(
                decision="teacher_review_warranted",
                rationale="No progress on the task.",
                evidence_used=["current_progress", "activity"],
                suggested_intervention=suggestion,
            ),
        )
        rows.append(review_to_row(review))
    return rows


def test_a_review_the_agent_writes_satisfies_every_check_of_the_real_table(supabase_stack):
    for row in review_rows():
        db.insert_and_roll_back("teacher_reviews", [row])
    for row in review_rows(suggestion=None):
        assert "suggested_intervention" not in row
        db.insert_and_roll_back("teacher_reviews", [row])


def test_a_review_row_is_a_review_the_dashboard_can_show():
    rows = review_rows()
    assert run_parser("reviews", rows)["reviews"] == len(rows) == 3


def test_the_agent_can_only_ask_for_a_review_from_a_stalled_evaluation(supabase_stack):
    from agent.assessment import AgentAssessment
    from agent.teacher_review import TeacherReviewStore

    assessment = AgentAssessment(
        decision="teacher_review_warranted", rationale="x", evidence_used=["activity"]
    )
    with pytest.raises(ValueError, match="eligible stalled"):
        TeacherReviewStore().request_teacher_review(
            request_for("stalled_progress", "normal", trend="improving"), assessment
        )
    with pytest.raises(ValueError, match="teacher-review assessment"):
        TeacherReviewStore().request_teacher_review(
            request_for("stalled_progress", "normal"),
            AgentAssessment(
                decision="continue_monitoring", rationale="x", evidence_used=["activity"]
            ),
        )
    # And the database refuses the same two things if anything else tried to write them.
    row = review_rows()[0]
    row["evaluation"]["progress"]["trend"] = "improving"
    with pytest.raises(RuntimeError, match="violates check constraint"):
        db.insert_and_roll_back("teacher_reviews", [row])
    row = review_rows()[0] | {"decision": "continue_monitoring"}
    with pytest.raises(RuntimeError, match="violates check constraint"):
        db.insert_and_roll_back("teacher_reviews", [row])


def test_the_agent_may_suggest_only_what_is_on_the_approved_menu(supabase_stack):
    from agent.assessment import AgentAssessment

    for invented in ("give_a_grade", "change_the_task", "Offer a short break", ""):
        with pytest.raises(ValidationError):
            AgentAssessment(
                decision="teacher_review_warranted",
                rationale="x",
                evidence_used=["activity"],
                suggested_intervention=invented,
            )
    row = review_rows()[0] | {"suggested_intervention": "give_a_grade"}
    with pytest.raises(RuntimeError, match="suggested_intervention"):
        db.insert_and_roll_back("teacher_reviews", [row])


def test_the_agent_is_given_task_facts_and_never_camera_data_or_expression():
    from agent.context_enricher import EnrichedEvaluationContext
    from agent.deep_agent import serialize_agent_context
    from shared.contracts import Activity

    activity = Activity(
        id="thumbs_up",
        name="Thumbs up",
        check_type="gesture",
        no_progress_seconds=3,
        success_threshold=0.7,
        review_threshold=0.5,
    )
    context = EnrichedEvaluationContext(
        request_for("stalled_progress_with_expression_context", "elevated"), activity
    )
    payload = json.loads(serialize_agent_context(context))
    assert set(payload) == {"request", "activity"}
    assert set(payload["request"]) == {
        "session_id",
        "seat_id",
        "activity_id",
        "observed_at",
        "progress",
        "escalation",
    }
    text = json.dumps(payload).lower()
    for word in ("image", "frame", "jpeg", "base64", "landmark", "sadness", "probability"):
        assert word not in text, word


# ---- 5. The teacher is told --------------------------------------------------------------------


def test_the_text_message_names_a_seat_and_nothing_else():
    from agent.assessment import AgentAssessment
    from agent.notifications import PhotonNotifier
    from agent.teacher_review import TeacherReviewStore

    review = TeacherReviewStore().request_teacher_review(
        request_for("stalled_progress_with_expression_context", "elevated"),
        AgentAssessment(
            decision="teacher_review_warranted",
            rationale="Sadness for a long time on thumbs up; the child seems upset.",
            evidence_used=["current_progress"],
            suggested_intervention="offer_break",
        ),
    )
    sent: list[tuple[str, str]] = []
    PhotonNotifier(lambda message, key: sent.append((message, key))).notify_pending_review(review)
    assert sent == [("Cues: Seat S1-P1 may need attention. Open Cues to review.", str(review.id))]
    message = sent[0][0].lower()
    leaks = {e.value for e in ExpressionLabel} | {"thumbs", "sad", "upset", "break", "score"}
    assert not any(word in message for word in leaks)
    resolved = review.model_copy(update={"status": "dismissed"})
    with pytest.raises(ValueError):
        PhotonNotifier(lambda message, key: None).notify_pending_review(resolved)


def test_send_results_mean_the_same_to_the_sender_the_server_and_the_database(supabase_stack):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    stored = db.function_source("record_teacher_notification_send")
    match = re.search(r"p_result not in \(([^)]*)\)", stored)
    assert match
    database = set(re.findall(r"'(\w+)'", match.group(1)))
    python = set(
        re.findall(
            r'"(accepted|target_not_allowed|provider_failure|network_failure)"',
            (root / "agent/notification_activation.py").read_text(),
        )
    )
    sender = re.search(r"SendCategory =([^;]*);", (root / "cues/src/send.ts").read_text())
    assert sender
    categories = set(re.findall(r'"(\w+)"', sender.group(1))) | {"accepted"}
    route = (root / "web/lib/notification-send.ts").read_text()
    typescript = set(
        re.findall(r'"(accepted|target_not_allowed|provider_failure|network_failure)"', route)
    )
    assert database == python == categories == typescript
    assert len(database) == 4


def test_registration_states_mean_the_same_to_the_dashboard_and_the_database(supabase_stack):
    from pathlib import Path

    stored: set[str] = set()
    for row in db.sql(
        "select pg_get_constraintdef(oid) as definition from pg_constraint "
        "where conrelid = 'public.teacher_notification_settings'::regclass and contype = 'c'"
    ):
        if "'unregistered'" in row["definition"] and "ANY" in row["definition"]:
            stored = set(re.findall(r"'([a-z]+)'::text", row["definition"]))
    source = (Path(__file__).resolve().parents[2] / "web/lib/notification-settings.ts").read_text()
    union = re.search(r"photon_registration_status: ([^;]*);", source)
    assert union
    assert (
        stored
        == set(re.findall(r'"(\w+)"', union.group(1)))
        == {
            "unregistered",
            "registering",
            "registered",
            "failed",
        }
    )


# ---- 6. The teacher answers, and the session ends ---------------------------------------------


def test_the_database_answers_the_dashboard_with_the_keys_it_reads(supabase_stack):
    assert not keys_in(
        "read_station_session", ["session", "latest_session", "station_runtime", "activities"]
    )
    assert not keys_in("get_or_create_my_default_station", ["station_id", "name", "created"])
    assert not keys_in("mark_seat_reviewed", ["closed", "marked_at"])
    assert not keys_in("claim_station_writer", ["granted", "held_seconds_ago"])


def columns_of(table: str) -> set[str]:
    return {
        row["column_name"]
        for row in db.sql(
            "select column_name from information_schema.columns "
            f"where table_schema = 'public' and table_name = '{table}'"
        )
    }


def test_the_review_columns_the_dashboard_selects_exist(supabase_stack):
    wanted = run_parser("menu", {})["review_columns"]
    assert set(wanted) <= columns_of("teacher_reviews"), sorted(
        set(wanted) - columns_of("teacher_reviews")
    )
    assert "suggested_intervention" in wanted


def test_the_long_term_record_has_class_counts_and_no_child_or_expression_data(supabase_stack):
    for table in ("session_summaries", "session_activity_spans"):
        stored = columns_of(table)
        assert stored, table
        assert not {c for c in stored if re.search(r"seat|child|student|name|expression", c)}


def test_the_insights_the_database_builds_have_the_contracts_keys(supabase_stack):
    import shared.contracts as contracts

    expected = {"from", "to"}
    for name in (
        "InsightsSummary",
        "InsightsTotals",
        "InsightsWeek",
        "InsightsSupport",
        "InsightsActivity",
        "InsightsHeat",
        "InsightsPrevious",
    ):
        expected |= set(getattr(contracts, name).model_fields)
    source = db.function_source("teacher_insights")
    missing = sorted(key for key in expected if f"'{key}'" not in source)
    assert not missing, f"teacher_insights no longer builds {missing}"


def test_expression_alone_never_asks_the_agent_to_evaluate():
    from agent.escalation import DEMO_ESCALATION_CONFIG, evaluate_escalation
    from agent.progress import ProgressState
    from shared.contracts import ExpressionContext

    strong = ExpressionContext(label="sadness", probability=0.99, duration_seconds=600)
    for trend in ("unknown", "improving", "completed"):
        for config in ({}, {"config": DEMO_ESCALATION_CONFIG}):
            decision = evaluate_escalation(ProgressState(trend, 600.0), strong, **config)
            assert decision.should_evaluate is False, trend
    # A strong expression does not shorten the wait before a stall counts at all.
    assert evaluate_escalation(ProgressState("stalled", 1.0), strong).should_evaluate is False
