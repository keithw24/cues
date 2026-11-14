"""Fixes from the senior review of vision/ (one test per fix)."""

import json
import threading
import time
import uuid

import numpy as np
import pytest

from vision.activities import Activity
from vision.status import SeatTracker


# ---- 1. pipeline survives errors; frame-rate counter is thread-safe --------
def test_rate_meter_is_safe_across_threads():
    from vision.pipeline import RateMeter

    meter, errors, stop = RateMeter(window_s=0.01), [], threading.Event()

    def reader():
        while not stop.is_set():
            try:
                meter.rate()
            except Exception as exc:  # pragma: no cover - would be the bug
                errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for _ in range(20000):
        meter.tick()
    stop.set()
    for t in threads:
        t.join()
    assert errors == []


def test_pipeline_keeps_running_after_a_frame_error():
    from vision.camera import FakeCamera
    from vision.pipeline import Pipeline

    pipe = Pipeline(FakeCamera(fps=60), [])
    calls = {"n": 0}
    real_step = pipe.step

    def flaky(frame):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom outside any stage")
        return real_step(frame)

    pipe.step = flaky
    pipe.start()
    try:
        deadline = time.monotonic() + 3
        while calls["n"] < 6 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        pipe.stop()
    assert calls["n"] >= 6 and pipe.errors == 1


# ---- 10. models load at start; a failing stage is switched off -------------
def test_pipeline_loads_models_before_start_and_drops_broken_stages():
    from vision.camera import FakeCamera
    from vision.pipeline import Pipeline

    class Good:
        name, rate_hz, loaded = "good", None, False

        def load(self):
            self.loaded = True

        def process(self, frame, ctx):
            pass

        def draw(self, image, ctx):
            pass

    class Broken(Good):
        name = "broken"

        def load(self):
            raise OSError("no network")

    good = Good()
    pipe = Pipeline(FakeCamera(), [good, Broken()])
    pipe.load()
    assert good.loaded and [s.name for s in pipe.stages] == ["good"]


def test_model_download_times_out_and_leaves_no_partial_file(tmp_path, monkeypatch):
    from vision import models

    def slow(*a, **k):
        assert k.get("timeout") == models.DOWNLOAD_TIMEOUT
        raise TimeoutError("stalled")

    monkeypatch.setattr(models.urllib.request, "urlopen", slow)
    with pytest.raises(TimeoutError):
        models.model_path("hand_landmarker.task", models_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


# ---- 2. needs_help / review survive a tracking loss ------------------------
@pytest.mark.parametrize("score,expected", [(0.0, "needs_help"), (0.5, "review")])
def test_status_is_restored_after_tracking_loss(score, expected):
    act = Activity("raise_hand", "r", "rule", 0.7, 0.4, 5)
    tr = SeatTracker("S1-P1", act)
    t = 0.0
    while t < 6:
        tr.update(t, score, True, True)
        t += 0.1
    assert tr.status == expected
    while t < 10:
        tr.update(t, None, False, False)
        t += 0.1
    assert tr.status == "tracking_lost"
    tr.update(t, score, True, True)
    assert tr.status == expected


# ---- 3. recognise mode: no flicker when the gesture dips for one frame -----
def test_recognizer_holds_gesture_through_a_one_frame_dip():
    from vision.stages.s46_recognize import Recognizer

    r = Recognizer(switch_seconds=0.5)
    for i in range(10):
        r.update(i * 0.1, "thumbs_up")
    assert r.update(1.0, None) == "thumbs_up"  # one frame: no change
    assert r.update(1.1, "thumbs_up") == "thumbs_up"
    for i in range(10):  # a 1 s dip is still held: the label must not blink off
        shown = r.update(1.2 + i * 0.1, None)
    assert shown == "thumbs_up"
    for i in range(10):
        shown = r.update(2.2 + i * 0.1, None)
    assert shown is None  # 1.5 s without the gesture: cleared


# ---- 4. recorder uses the same model as the live service ------------------
def test_recorder_uses_the_gesture_recognizer(monkeypatch):
    from vision import models, record

    used = {}

    def fake_recognizer(num_hands=4):
        used["model"] = "gesture_recognizer"
        raise SystemExit("stop before opening the camera")

    monkeypatch.setattr(models, "gesture_recognizer", fake_recognizer)
    with pytest.raises(SystemExit):
        record.main(["custom_gesture_01", "target", "--no-preview", "--delay", "0"])
    assert used == {"model": "gesture_recognizer"}


# ---- 5. an unreadable hand is skipped, not fatal ---------------------------
def test_score_gesture_skips_unreadable_hands(tmp_path):
    from vision import activities
    from vision.gestures import templates as tpl
    from vision.gestures.normalize import normalize
    from vision.perception import Hand
    from vision.stages.s30_gestures import MatcherCache, score_gesture
    from vision.tests.hands import PERSONS_RIGHT, thumbs_up_back

    t = tpl.Templates("custom_gesture_01")
    t.add("target", [normalize(thumbs_up_back(), PERSONS_RIGHT)] * 3)
    tpl.save(t, tmp_path)
    good = Hand(thumbs_up_back(), PERSONS_RIGHT, "S1-P1")
    broken = Hand(np.zeros((21, 3), np.float32), PERSONS_RIGHT, "S1-P1")  # all points equal
    act = activities.get("custom_gesture_01")
    score, hand, _, _ = score_gesture(act, [broken, good], MatcherCache(tmp_path))
    assert hand is good and score > 0.9
    score, hand, reason, _ = score_gesture(act, [broken], MatcherCache(tmp_path))
    assert score is None and "unreadable" in reason


# ---- 7. a session id is required when Supabase is on -----------------------
def test_supabase_without_session_id_fails_at_start(monkeypatch):
    from vision import events, supabase_client

    monkeypatch.setattr(supabase_client, "get_client", lambda: object())
    monkeypatch.setenv("CUES_FLAG_VISION_SUPABASE_EVENTS", "1")
    monkeypatch.delenv("CUES_SESSION_ID", raising=False)
    with pytest.raises(RuntimeError, match="CUES_SESSION_ID"):
        events.emitter_from_env()


def test_task_sync_without_session_id_fails_at_start(monkeypatch):
    from vision import activity_sync, supabase_client

    monkeypatch.setattr(supabase_client, "get_client", lambda: object())
    monkeypatch.setenv("CUES_FLAG_VISION_ACTIVITY_SYNC", "1")
    monkeypatch.delenv("CUES_SESSION_ID", raising=False)
    with pytest.raises(RuntimeError, match="CUES_SESSION_ID"):
        activity_sync.sync_from_env()


def test_offline_still_starts_with_a_new_session(monkeypatch):
    from vision import events

    monkeypatch.delenv("CUES_FLAG_VISION_SUPABASE_EVENTS", raising=False)
    monkeypatch.delenv("CUES_SESSION_ID", raising=False)
    emitter = events.emitter_from_env()
    try:
        assert isinstance(emitter.session_id, uuid.UUID)
    finally:
        emitter.close()


# ---- 8. local seat_state keeps only the latest row per person -------------
def test_local_seat_state_is_not_an_expression_history(tmp_path):
    from vision.events import JsonlSink

    sink = JsonlSink(tmp_path)
    for i, label in enumerate(["neutral", "happiness", "sadness"]):
        sink.write_seat_state({"seat_id": "S1-P1", "n": i, "expression_context": {"label": label}})
    sink.write_seat_state({"seat_id": "S1-P2", "n": 9})
    stored = json.loads((tmp_path / "seat_state.json").read_text())
    assert set(stored) == {"S1-P1", "S1-P2"}
    assert stored["S1-P1"]["expression_context"]["label"] == "sadness"  # latest only
    assert not (tmp_path / "seat_state.jsonl").exists()


# ---- 9. a lost camera is reported and reopened ----------------------------
def test_camera_reconnects_after_losing_frames(monkeypatch):
    from vision import camera

    class FakeCap:
        def __init__(self, frames):
            self.frames = frames

        def isOpened(self):
            return True

        def read(self):
            if self.frames > 0:
                self.frames -= 1
                return True, np.zeros((720, 1280, 3), np.uint8)
            return False, None

        def release(self):
            pass

    caps = [FakeCap(3), FakeCap(10**6)]  # first one dies after 3 frames
    monkeypatch.setattr(camera, "open_capture", lambda index: caps.pop(0))
    monkeypatch.setattr(camera.OpenCVCamera, "LOST_SECONDS", 0.05)
    cam = camera.OpenCVCamera()
    cam.start()
    try:
        deadline = time.monotonic() + 3
        while caps and time.monotonic() < deadline:  # second capture opened?
            time.sleep(0.01)
        time.sleep(0.1)
        assert not caps
        assert cam.is_open and cam.latest().index > 3
    finally:
        cam.stop()


def test_camera_reports_not_open_while_disconnected():
    from vision.camera import OpenCVCamera

    cam = OpenCVCamera()
    cam._running, cam._device_ok = True, False
    assert cam.is_open is False


def test_health_shows_errors_and_frame_age():
    from vision.camera import FakeCamera
    from vision.pipeline import Pipeline

    pipe = Pipeline(FakeCamera(), [])
    h = pipe.health()
    assert h["errors"] == 0
    assert "frame_age_seconds" in h
