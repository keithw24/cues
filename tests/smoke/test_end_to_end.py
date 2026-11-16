"""Smoke test: the whole Cues workflow, end to end, on the local Supabase.

A teacher signs up and starts a session; the real vision service (fake camera) takes the
station and follows the session; a child who stops making progress is published with vision's
real writer; the agent's real runtime reads that, reaches a review decision (stub LLM, real
everything else), stores a pending review and sends the teacher text through the real
notifier; the dashboard's real TypeScript parsers read everything back; the teacher marks
the child reviewed and the agent side sees it.

    supabase start
    uv run pytest tests/smoke -v -s

Writes only to the local database, under a throwaway teacher that is removed afterwards. No
camera, no network, no text message: the final send is captured, not delivered.
"""

import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

from shared.contracts import Activity, SeatState
from tests.support import local_supabase as db
from tests.support.typescript import run_parser

pytestmark = pytest.mark.smoke
VISION_PORT = 8765
PASSWORD = "smoke-Passw0rd!"


def wait_for(description, check, timeout, interval=0.5):
    """Poll until check() returns something truthy; fail with what we were waiting for."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout}s waiting for: {description} (last: {last!r})")


class Teacher:
    """A throwaway teacher account and the station the app gives them."""

    def __init__(self, stack):
        self.stack = stack
        self.email = f"smoke-{uuid.uuid4().hex[:10]}@example.test"
        status, body = db.http(
            "POST",
            "/auth/v1/signup",
            {"email": self.email, "password": PASSWORD},
            key=stack.publishable_key,
        )
        assert status == 200, body
        status, body = db.http(
            "POST",
            "/auth/v1/token?grant_type=password",
            {"email": self.email, "password": PASSWORD},
            key=stack.publishable_key,
        )
        assert status == 200, body
        self.token, self.id = body["access_token"], body["user"]["id"]
        self.station = self.rpc("get_or_create_my_default_station", {})["station_id"]
        self.seat = f"{self.station}-P1"

    def rpc(self, name, args):
        status, body = db.http(
            "POST", f"/rest/v1/rpc/{name}", args, key=self.stack.publishable_key, token=self.token
        )
        assert status == 200, f"{name} -> {status} {body}"
        return body

    def read(self, path):
        status, body = db.http(
            "GET", f"/rest/v1/{path}", key=self.stack.publishable_key, token=self.token
        )
        assert status == 200, f"{path} -> {status} {body}"
        return body

    def start_activity(self, activity_id, session=None):
        return self.rpc(
            "start_station_activity",
            {
                "p_station_id": self.station,
                "p_activity_id": activity_id,
                "p_expected_session_id": session["id"] if session else None,
                "p_expected_revision": session["revision"] if session else None,
            },
        )

    def end_session(self, session):
        return self.rpc(
            "end_station_session",
            {
                "p_station_id": self.station,
                "p_expected_session_id": session["id"],
                "p_expected_revision": session["revision"],
            },
        )

    def cleanup(self):
        station = self.station.replace("'", "''")
        for statement in (
            f"delete from interventions where review_id in (select id from teacher_reviews "
            f"where session_id in (select id from sessions where station_id = '{station}'))",
            f"delete from teacher_reviews where session_id in "
            f"(select id from sessions where station_id = '{station}')",
            f"delete from seat_review_marks where session_id in "
            f"(select id from sessions where station_id = '{station}')",
            f"delete from events where station_id = '{station}'",
            f"delete from seat_state where seat_id like '{station}-%'",
            f"delete from station_runtime where station_id = '{station}'",
            f"delete from station_writers where station_id = '{station}'",
            f"delete from sessions where station_id = '{station}'",
            f"delete from seats where station_id = '{station}'",
            f"delete from station_teachers where station_id = '{station}'",
            f"delete from station_pairing_codes where station_id = '{station}'",
            f"delete from stations where id = '{station}'",
            f"delete from auth.users where id = '{self.id}'",
        ):
            try:
                db.execute(statement)
            except RuntimeError:
                pass  # best effort: the next run uses a fresh teacher anyway


@pytest.fixture(scope="module")
def teacher(supabase_stack):
    person = Teacher(supabase_stack)
    yield person
    person.cleanup()


@pytest.fixture(scope="module")
def vision(supabase_stack, teacher):
    """The real vision service on a fake camera, following this teacher's station."""
    env = {
        **os.environ,
        "SUPABASE_URL": supabase_stack.api_url,
        "SUPABASE_SERVICE_ROLE_KEY": supabase_stack.secret_key,
        "CUES_CAMERA": "fake",
        "CUES_STATION_ID": "",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "vision.app:app", "--port", str(VISION_PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{VISION_PORT}"

    def healthy():
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                return json.load(response)
        except Exception:
            return None

    try:
        wait_for("vision /health", healthy, 60)
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def runtime_row(station):
    rows = db.sql(
        f"select status, activity_id, revision from station_runtime where station_id = '{station}'"
    )
    return rows[0] if rows else None


def test_vision_takes_the_station_and_follows_the_teachers_session(vision, teacher):
    import json
    import urllib.request

    request = urllib.request.Request(
        f"{vision}/config",
        json.dumps({"station_id": teacher.station}).encode(),
        {"Content-Type": "application/json"},
    )
    assert json.load(urllib.request.urlopen(request, timeout=5))["station_id"] == teacher.station

    session = teacher.start_activity("raise_hand")
    wait_for(
        "vision reports the session as ready on the teacher's activity",
        lambda: (
            (r := runtime_row(teacher.station))
            and r["status"] == "ready"
            and r["activity_id"] == "raise_hand"
            and r
        ),
        30,
    )
    # The dashboard reads the same thing back and its parsers accept it.
    snapshot = teacher.rpc("read_station_session", {"p_station_id": teacher.station})
    assert run_parser("session", snapshot, teacher.station)["id"] == session["id"]
    assert run_parser("runtime", snapshot, teacher.station)["status"] == "ready"

    # One camera per station: a second camera is refused while this one holds the lease.
    other = db.sql(
        f"select public.claim_station_writer('{teacher.station}', '{uuid.uuid4()}', 10) as result"
    )[0]["result"]
    assert other["granted"] is False

    # A reset (same activity, new revision) is followed at once when the dashboard asks, not
    # at the next poll: vision's writes for the old revision are rejected until it does.
    session = teacher.start_activity("raise_hand", session)
    nudge = urllib.request.Request(
        f"{vision}/config",
        json.dumps({"station_id": teacher.station, "refresh": True}).encode(),
        {"Content-Type": "application/json"},
    )
    urllib.request.urlopen(nudge, timeout=5)
    wait_for(
        "vision follows the reset within half a second of being asked",
        lambda: (r := runtime_row(teacher.station)) and r["revision"] == session["revision"],
        0.5,
        interval=0.05,
    )

    ended = teacher.end_session(session)
    assert ended["ended_at"] is not None
    wait_for(
        "vision goes idle after the session ends",
        lambda: (r := runtime_row(teacher.station)) and r["status"] == "idle",
        30,
    )


class StubModel(FakeMessagesListChatModel):
    """The only fake in this test: an LLM that always asks for a teacher review."""

    offered: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self


def review_call():
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": "review",
                "name": "request_teacher_review",
                "args": {
                    "rationale": "The child has not progressed on the task.",
                    "suggested_intervention": "show_example",
                    "evidence_used": ["current_progress"],
                },
            }
        ],
    )


def test_a_stalled_child_becomes_a_review_the_teacher_can_see_and_close(
    supabase_stack, teacher, vision, tmp_path
):
    from agent.escalation import DEMO_ESCALATION_CONFIG
    from agent.notifications import PhotonNotifier
    from agent.runtime import create_seat_state_runtime
    from agent.seat_state_runtime import SupabaseSeatStateSource
    from shared.supabase_client import get_client
    from vision.activities import load_activities
    from vision.events import Emitter, SupabaseSink

    session = teacher.start_activity("raise_hand")
    session_id = uuid.UUID(session["id"])
    client = get_client(supabase_stack.api_url, supabase_stack.secret_key)

    # --- vision: publish a child who is tracked but makes no progress, with vision's writer
    emitter = Emitter(SupabaseSink(client), session_id=session_id, station_id=teacher.station)
    stop = threading.Event()

    def publish():
        while not stop.is_set():
            emitter.update_seat_state(
                SeatState(
                    seat_id=teacher.seat,
                    session_id=session_id,
                    status="in_progress",
                    updated_at=datetime.now(UTC),
                    activity_id="raise_hand",
                    tracking_valid=True,
                    session_revision=session["revision"],
                    task_score=None,
                )
            )
            stop.wait(1.0)

    publisher = threading.Thread(target=publish, daemon=True)
    publisher.start()

    # --- agent: the real runtime, the real Supabase source and review store; fake LLM + sender
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        f"SUPABASE_URL={supabase_stack.api_url}\n"
        f"SUPABASE_SERVICE_ROLE_KEY={supabase_stack.secret_key}\n"
    )
    texts: list[tuple[str, str]] = []
    activities = [
        Activity(
            id=a.id,
            name=a.name,
            check_type=a.check_type,
            no_progress_seconds=a.no_progress_seconds,
            success_threshold=a.success_threshold,
            review_threshold=a.review_threshold,
        )
        for a in load_activities().values()
    ]
    source = SupabaseSeatStateSource(client, station_provider=lambda: teacher.station)
    runtime = create_seat_state_runtime(
        StubModel(responses=[review_call()]),
        activities,
        env_file=env_file,
        notifier=PhotonNotifier(lambda message, key: texts.append((message, key))),
        source=source,
        progress_window_seconds=2,
        escalation_config=DEMO_ESCALATION_CONFIG,
        poll_seconds=0.5,
        publish_progress=True,
    )

    # Count what the agent publishes: progress is written only when it changes.
    published: list[str] = []
    publish = runtime.pipeline.publisher

    def counting_publisher(snapshot, progress, recent, stalled_since=None):
        published.append(progress.trend)
        return publish(snapshot, progress, recent, stalled_since)

    runtime.pipeline.publisher = counting_publisher
    processed = 0

    def pending():
        nonlocal processed
        processed += len(runtime.run_once())
        return teacher.read("teacher_reviews?status=eq.pending&select=*")

    try:
        reviews = wait_for("the agent stores a pending review for the stalled child", pending, 45)
    finally:
        stop.set()
        publisher.join(timeout=5)
        emitter.close()

    review = reviews[0]
    assert review["seat_id"] == teacher.seat and review["activity_id"] == "raise_hand"
    assert str(review["session_id"]) == session["id"]

    # --- the teacher text: sent once, minimal, nothing about the child's state or video
    assert len(texts) == 1, texts
    message, idempotency_key = texts[0]
    assert message == f"Cues: Seat {teacher.seat} may need attention. Open Cues to review."
    assert idempotency_key == review["id"]

    # --- evaluated progress: published only on change, with the stall's start time
    assert processed > len(published), (processed, published)
    assert all(a != b for a, b in zip(published, published[1:], strict=False)), published
    state = teacher.read(f"seat_state?seat_id=eq.{teacher.seat}&select=*")[0]
    progress = state["evaluated_progress"]
    assert progress["trend"] == "stalled" and progress["stalled_since"], progress
    trends = [entry["progress"]["trend"] for entry in progress["recent"]]
    assert all(a != b for a, b in zip(trends, trends[1:], strict=False)), trends

    # --- the dashboard shows it while the agent is alive, and hides it once it goes quiet
    station = teacher.rpc("read_station_session", {"p_station_id": teacher.station})
    seen = station["station_runtime"]["agent_seen_at"]
    assert seen, "the agent's station read did not stamp agent_seen_at"
    run_parser("runtime", station, teacher.station)
    seen_ms = datetime.fromisoformat(seen).timestamp() * 1000
    shown = run_parser("progress", {"row": state, "now": seen_ms + 1000, "agent_seen_at": seen})
    assert shown["visible"] and shown["trend"] == "stalled", shown
    hidden = run_parser("progress", {"row": state, "now": seen_ms + 25000, "agent_seen_at": seen})
    assert not hidden["visible"], hidden

    # --- the dashboard reads all of it back through its real parsers
    snapshot = {
        "seats": teacher.read(f"seats?station_id=eq.{teacher.station}&select=*"),
        "states": teacher.read("seat_state?select=*"),
        "activities": teacher.read("activities?select=id,name"),
        "stations": teacher.read(f"stations?id=eq.{teacher.station}&select=id,name"),
    }
    assert run_parser("snapshot", snapshot)["states"] >= 1
    assert run_parser("reviews", teacher.read("teacher_reviews?select=*"))["reviews"] == 1

    # --- the suggested support: from the approved menu, approved by the teacher
    assert review["suggested_intervention"] == "show_example"
    approved = teacher.rpc(
        "approve_review_intervention", {"review_id": review["id"], "action": None}
    )
    assert approved["action"] == "show_example"
    status = teacher.read(f"teacher_reviews?id=eq.{review['id']}&select=status")[0]["status"]
    assert status == "confirmed"

    # --- the teacher marks the child reviewed: the review closes and the agent side sees it
    teacher.rpc("mark_seat_reviewed", {"p_session_id": session["id"], "p_seat_id": teacher.seat})
    closed = teacher.read(f"teacher_reviews?id=eq.{review['id']}&select=status")[0]["status"]
    assert closed != "pending"
    source.fetch()  # the next poll brings the mark with the snapshot
    marks = source.fetch_marks()
    assert (session_id, teacher.seat) in marks
    assert not teacher.read("teacher_reviews?status=eq.pending&select=id")

    teacher.end_session(session)
