"""Supabase sink filtering, current-task sync, and the recording endpoint."""

import pytest

from vision.activities import CurrentTasks


class FakeQuery:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.filters = {}

    def upsert(self, row, on_conflict=None):
        self.store.setdefault(self.table, []).append(row)
        return self

    def insert(self, row):
        return self.upsert(row)

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _):
        return self

    def execute(self):
        rows = [
            r
            for r in self.store.get(self.table, [])
            if all(r.get(k) == v for k, v in self.filters.items())
        ]
        return type("R", (), {"data": rows})()


class FakeClient:
    def __init__(self, store=None):
        self.store = store if store is not None else {}

    def table(self, name):
        return FakeQuery(self.store, name)


# ---- Supabase sink ---------------------------------------------------------
def test_seat_state_upsert_keeps_tracking_valid():
    from vision.events import SupabaseSink

    client = FakeClient()
    SupabaseSink(client).write_seat_state(
        {"seat_id": "S1-P1", "status": "done", "tracking_valid": True, "task_score": 0.9}
    )
    sent = client.store["seat_state"][0]
    assert sent["tracking_valid"] is True
    assert sent["status"] == "done" and sent["task_score"] == 0.9


# ---- current task sync -----------------------------------------------------
def session_store(activity_id):
    return {"sessions": [{"id": "sess-1", "current_activity_id": activity_id}]}


def test_sync_applies_the_session_task():
    from vision.activity_sync import ActivitySync

    store = session_store("raise_hand")
    tasks = CurrentTasks("thumbs_up")
    sync = ActivitySync(FakeClient(store), "sess-1", tasks=tasks)
    assert sync.check_once() == "raise_hand"
    assert tasks.for_seat("S1-P1") == "raise_hand"
    assert sync.check_once() is None  # unchanged: nothing to do
    store["sessions"][0]["current_activity_id"] = "custom_gesture_01"
    assert sync.check_once() == "custom_gesture_01"


def test_sync_ignores_unknown_tasks_and_missing_sessions():
    from vision.activity_sync import ActivitySync

    tasks = CurrentTasks("thumbs_up")
    assert ActivitySync(FakeClient(session_store("juggling")), "sess-1", tasks).check_once() is None
    assert ActivitySync(FakeClient({}), "sess-1", tasks).check_once() is None
    assert tasks.for_seat("S1-P1") == "thumbs_up"


def test_sync_is_off_without_the_flag(monkeypatch):
    from vision.activity_sync import sync_from_env

    monkeypatch.delenv("CUES_FLAG_VISION_ACTIVITY_SYNC", raising=False)
    assert sync_from_env() is None


# ---- recording endpoint ----------------------------------------------------
def thumbs_ctx():
    from vision.perception import Hand
    from vision.tests.test_perception import hand_points

    return {"hands": {"S1-P1": [Hand(hand_points((0.3, 0.5)), "Right", "S1-P1")]}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from vision.app import create_app
    from vision.camera import FakeCamera
    from vision.gestures import templates as tpl
    from vision.pipeline import Pipeline

    monkeypatch.setenv("CUES_FLAG_VISION_GESTURES", "1")
    monkeypatch.setattr(tpl, "TEMPLATES_DIR", tmp_path)
    pipeline = Pipeline(FakeCamera(), [])
    with TestClient(create_app(pipeline)) as c:
        pipeline.ctx.update(thumbs_ctx())
        yield c


def test_record_endpoint_saves_examples_from_live_hands(client, tmp_path):
    r = client.post(
        "/templates/record",
        json={"activity_id": "custom_gesture_01", "label": "target", "seconds": 0.3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["captured"] >= 2 and body["target_examples"] == body["captured"]
    assert (tmp_path / "custom_gesture_01.json").exists()
    assert client.get("/templates/custom_gesture_01").json()["target_examples"] == body["captured"]
    assert client.delete("/templates/custom_gesture_01").json() == {"deleted": True}


def test_record_endpoint_rejects_rule_tasks_and_empty_seats(client):
    r = client.post("/templates/record", json={"activity_id": "raise_hand", "label": "target"})
    assert r.status_code == 422
    r = client.post(
        "/templates/record",
        json={
            "activity_id": "custom_gesture_01",
            "label": "target",
            "seconds": 0.2,
            "seat_id": "S1-P4",
        },
    )
    assert r.status_code == 422 and "no hand" in r.json()["detail"]
