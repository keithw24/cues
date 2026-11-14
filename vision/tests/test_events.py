import json
import os

import pytest
from vision.events import Emitter, Event, JsonlSink


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


def test_event_row_matches_contract():
    event = Event(type="attempt_success", seat_id="S1-L", activity_id="raise_hand", score=0.9)
    row = event.to_row()
    assert set(row) == {
        "session_id",
        "station_id",
        "seat_id",
        "type",
        "activity_id",
        "score",
        "payload",
        "created_at",
    }
    assert row["payload"] == {"source": "auto"}
    assert row["created_at"].endswith("Z")


def test_event_rejects_unknown_type_and_bad_score():
    with pytest.raises(ValueError):
        Event(type="emotion_detected", seat_id="S1-L")
    with pytest.raises(ValueError):
        Event(type="attempt_miss", seat_id="S1-L", score=1.5)


def test_emitter_fills_session_and_station():
    sink = MemorySink()
    emitter = Emitter(sink, session_id="sess-1", station_id="S1")
    emitter.emit(Event(type="attempt_miss", seat_id="S1-R", activity_id="thumbs_up", score=0.3))
    emitter.close()
    assert sink.events[0]["session_id"] == "sess-1"
    assert sink.events[0]["station_id"] == "S1"


def test_seat_state_only_sends_given_fields():
    sink = MemorySink()
    emitter = Emitter(sink, session_id="sess-1")
    emitter.update_seat_state("S1-L", status="in_progress")
    emitter.close()
    row = sink.states[0]
    assert row["seat_id"] == "S1-L"
    assert row["status"] == "in_progress"
    assert "task_score" not in row
    assert "updated_at" in row


def test_seat_state_rejects_unknown_status():
    emitter = Emitter(MemorySink())
    with pytest.raises(ValueError):
        emitter.update_seat_state("S1-L", status="struggling")
    emitter.close()


def test_failed_write_goes_to_fallback():
    fallback = MemorySink()
    emitter = Emitter(FailingSink(), fallback=fallback)
    emitter.emit(Event(type="tracking_lost", seat_id="S1-L"))
    emitter.update_seat_state("S1-L", status="tracking_lost")
    emitter.close()
    assert len(fallback.events) == 1
    assert len(fallback.states) == 1


def test_jsonl_sink_appends_lines(tmp_path):
    sink = JsonlSink(tmp_path)
    emitter = Emitter(sink)
    emitter.emit(Event(type="attempt_success", seat_id="S1-L"))
    emitter.emit(Event(type="attempt_miss", seat_id="S1-L"))
    emitter.close()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["attempt_success", "attempt_miss"]


@pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")),
    reason="needs SUPABASE_URL and SUPABASE_KEY",
)
def test_supabase_round_trip():
    from vision.events import SupabaseSink
    from vision.supabase_client import get_client

    client = get_client()
    marker = "S1-TEST"
    emitter = Emitter(SupabaseSink(client))
    emitter.emit(Event(type="attempt_success", seat_id=marker, activity_id="raise_hand", score=1))
    emitter.close()
    rows = client.table("events").select("*").eq("seat_id", marker).execute().data
    assert rows
