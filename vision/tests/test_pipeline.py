import time

import cv2
import numpy as np
import pytest

from vision.camera import FakeCamera, Frame, OpenCVCamera
from vision.pipeline import Pipeline, RateMeter, discover_stages


class RecordingStage:
    def __init__(self, name="rec", rate_hz=None):
        self.name = name
        self.rate_hz = rate_hz
        self.calls = 0

    def process(self, frame, ctx):
        self.calls += 1
        ctx[self.name] = frame.index

    def draw(self, image, ctx):
        image[0, 0] = (0, 0, 255)


class BrokenStage:
    name = "broken"
    rate_hz = None

    def process(self, frame, ctx):
        raise ValueError("boom")

    def draw(self, image, ctx):
        raise ValueError("boom")


def make_frame(index=1):
    return Frame(image=np.zeros((480, 640, 3), np.uint8), timestamp=time.monotonic(), index=index)


def test_step_runs_stages_and_returns_jpeg():
    stage = RecordingStage()
    p = Pipeline(FakeCamera(), [stage])
    jpeg = p.step(make_frame(7))
    assert stage.calls == 1
    assert p.ctx["rec"] == 7
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (480, 640, 3)


def test_draw_does_not_modify_original_frame():
    frame = make_frame()
    Pipeline(FakeCamera(), [RecordingStage()]).step(frame)
    assert frame.image[0, 0].tolist() == [0, 0, 0]


def test_rate_limited_stage_skips_frames():
    slow = RecordingStage("slow", rate_hz=1.0)
    p = Pipeline(FakeCamera(), [slow])
    for i in range(5):
        p.step(make_frame(i + 1))
    assert slow.calls == 1


def test_broken_stage_does_not_stop_pipeline():
    good = RecordingStage()
    p = Pipeline(FakeCamera(), [BrokenStage(), good])
    assert p.step(make_frame())
    assert good.calls == 1


def test_rate_meter():
    m = RateMeter(window_s=10)
    for i in range(11):
        m.tick(now=100 + i * 0.1)
    assert m.rate(now=101.0) == pytest.approx(10.0)


def test_discover_stages_with_perception_flags_off(monkeypatch):
    for name in ("HANDS", "FACES", "GESTURES", "RAISE_HAND", "EXPRESSION", "TASK_STATUS"):
        monkeypatch.delenv(f"CUES_FLAG_VISION_{name}", raising=False)
    assert [s.name for s in discover_stages()] == ["seats"]


def test_discover_stages_with_perception_flags_on(monkeypatch):
    for name in ("HANDS", "FACES", "GESTURES", "RAISE_HAND", "EXPRESSION", "TASK_STATUS"):
        monkeypatch.setenv(f"CUES_FLAG_VISION_{name}", "1")
    names = [s.name for s in discover_stages()]
    assert names == ["seats", "hands", "faces", "gestures", "raise_hand", "expression", "status"]


def test_pipeline_runs_with_fake_camera():
    p = Pipeline(FakeCamera(fps=60), [RecordingStage()])
    p.start()
    try:
        index, jpeg = p.wait_for_jpeg(after=0, timeout=2)
        assert jpeg is not None
        time.sleep(0.5)
        health = p.health()
        assert health["camera_open"] is True
        assert health["fps"] > 0
        assert "rec" in health["stages"]
    finally:
        p.stop()


@pytest.mark.hardware
def test_real_camera_produces_frames():
    cam = OpenCVCamera()
    cam.start()
    try:
        deadline = time.monotonic() + 5
        while cam.latest() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        frame = cam.latest()
        assert frame is not None
        assert frame.image.shape == (480, 640, 3)
    finally:
        cam.stop()
