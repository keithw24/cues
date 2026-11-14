import json
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from shared.contracts import Event, SeatState
from vision.events import Emitter, JsonlSink

SESSION_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
NOW = datetime(2026, 11, 14, 2, tzinfo=UTC)


class MemorySink:
    def __init__(self):
        self.events = []
        self.states = []

    def write_event(self, row):
        self.events.append(row)

    def write_seat_state(self, row):
        self.states.append(row)


class FailingSink:
    def write_event(self, row):
        raise ConnectionError("offline")

    def write_seat_state(self, row):
        raise ConnectionError("offline")


def event(**changes):
    return Event.model_validate(
        dict(
            session_id=SESSION_ID,
            station_id="S1",
            seat_id="S1-L",
            type="attempt_miss",
            activity_id="raise_hand",
            score=0.3,
            created_at=NOW,
        )
        | changes
    )


def state(**changes):
    return SeatState.model_validate(
        dict(session_id=SESSION_ID, seat_id="S1-L", status="in_progress", updated_at=NOW) | changes
    )


@pytest.fixture
def make_emitter():
    emitters = []

    def make(sink, **kwargs):
        emitter = Emitter(sink, **kwargs)
        emitters.append(emitter)
        return emitter

    yield make
    for emitter in emitters:
        emitter.close()


def test_vision_uses_canonical_event():
    from vision import events

    assert events.Event is Event
    assert events.SeatState is SeatState


def test_emitter_serializes_shared_event_without_overriding_ids(make_emitter):
    sink = MemorySink()
    emitter = make_emitter(sink, station_id="OTHER")
    model = event()
    before = model.model_dump()
    emitter.emit(model)
    emitter.flush()
    row = sink.events[0]
    assert Event.model_validate(row) == model
    assert row["session_id"] == str(SESSION_ID)
    assert row["station_id"] == "S1"
    assert row["created_at"] == "2026-11-14T02:00:00Z"
    assert model.model_dump() == before
    json.dumps(row)  # No UUID, enum, or datetime objects reach sinks.


def test_emitter_defaults_are_valid_for_producer_models(make_emitter):
    emitter = make_emitter(MemorySink(), session_id=str(SESSION_ID))
    assert emitter.session_id == SESSION_ID
    assert isinstance(make_emitter(MemorySink()).session_id, UUID)
    with pytest.raises(ValueError):
        Emitter(MemorySink(), session_id="sess-1")


def test_seat_state_sends_complete_snapshot_and_clears_old_values(make_emitter):
    sink = MemorySink()
    emitter = make_emitter(sink)
    emitter.update_seat_state(
        state(
            activity_id="raise_hand",
            task_score=0.7,
            expression_context={"label": "neutral", "probability": 0.74},
        )
    )
    emitter.update_seat_state(state(status="idle"))
    emitter.flush()
    row = sink.states[-1]
    assert SeatState.model_validate(row).status == "idle"
    assert row["session_id"] == str(SESSION_ID)
    assert row["activity_id"] is None
    assert row["task_score"] is None
    assert row["expression_context"] is None
    assert row["updated_at"] == "2026-11-14T02:00:00Z"
    json.dumps(row)


@pytest.mark.parametrize("target", ["event", "state"])
def test_mutated_invalid_models_are_rejected_before_writing(make_emitter, target):
    sink = MemorySink()
    emitter = make_emitter(sink)
    if target == "event":
        model = event()
        model.score = 2
        with pytest.raises(ValidationError):
            emitter.emit(model)
    else:
        model = state()
        model.task_score = 2
        with pytest.raises(ValidationError):
            emitter.update_seat_state(model)
    emitter.flush()
    assert sink.events == []
    assert sink.states == []


def test_queued_rows_are_detached_from_mutable_models(make_emitter):
    sink = MemorySink()
    emitter = make_emitter(sink)
    model = event(payload={"metadata": {"source": "auto"}})
    emitter.emit(model)
    model.payload["metadata"]["source"] = "changed"
    emitter.flush()
    assert sink.events[0]["payload"]["metadata"]["source"] == "auto"


def test_failed_write_goes_to_fallback(make_emitter):
    fallback = MemorySink()
    emitter = make_emitter(FailingSink(), fallback=fallback)
    emitter.emit(event(type="tracking_lost", score=None))
    emitter.update_seat_state(state(status="tracking_lost"))
    emitter.flush()
    assert Event.model_validate(fallback.events[0]).type == "tracking_lost"
    assert SeatState.model_validate(fallback.states[0]).status == "tracking_lost"


def test_jsonl_sink_appends_valid_shared_contracts(tmp_path, make_emitter):
    emitter = make_emitter(JsonlSink(tmp_path))
    emitter.emit(event(type="attempt_success"))
    emitter.emit(event())
    emitter.update_seat_state(state())
    emitter.flush()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert [Event.model_validate_json(line).type for line in lines] == [
        "attempt_success",
        "attempt_miss",
    ]
    latest = json.loads((tmp_path / "seat_state.json").read_text())
    assert SeatState.model_validate(latest["S1-L"]).seat_id == "S1-L"


def test_demo_emits_shared_contracts(monkeypatch, capsys):
    from vision import events

    sink = MemorySink()
    emitter = Emitter(sink, session_id=SESSION_ID, station_id="DEMO")
    monkeypatch.setattr(events, "emitter_from_env", lambda: emitter)
    events.main(["--demo"])
    assert Event.model_validate(sink.events[0]).station_id == "DEMO"
    assert SeatState.model_validate(sink.states[0]).seat_id == "DEMO-L"
    assert "DEMO-L" in capsys.readouterr().out


@pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
    reason="needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY",
)
def test_supabase_round_trip(make_emitter):
    from vision.events import SupabaseSink
    from vision.supabase_client import get_client

    client = get_client()
    marker = "S1-TEST"
    emitter = make_emitter(SupabaseSink(client))
    emitter.emit(event(type="attempt_success", seat_id=marker, score=1))
    emitter.flush()
    rows = client.table("events").select("*").eq("seat_id", marker).execute().data
    assert rows


def test_flag_off_keeps_events_local_even_with_keys(monkeypatch):
    from vision import events, flags, supabase_client

    monkeypatch.setattr(supabase_client, "get_client", lambda: object())
    monkeypatch.setenv("CUES_FLAG_VISION_SUPABASE_EVENTS", "0")
    flags.load_registry.cache_clear()
    emitter = events.emitter_from_env()
    try:
        assert isinstance(emitter.sink, JsonlSink)
        assert emitter.fallback is None
    finally:
        emitter.close()


def test_flag_on_with_keys_uses_supabase(monkeypatch):
    from vision import events, flags, supabase_client

    monkeypatch.setattr(supabase_client, "get_client", lambda: object())
    monkeypatch.setenv("CUES_FLAG_VISION_SUPABASE_EVENTS", "1")
    flags.load_registry.cache_clear()
    emitter = events.emitter_from_env()
    try:
        assert isinstance(emitter.sink, events.SupabaseSink)
        assert isinstance(emitter.fallback, JsonlSink)
    finally:
        emitter.close()
