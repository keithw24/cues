from fastapi.testclient import TestClient

from vision.app import create_app, mjpeg_parts
from vision.camera import FakeCamera
from vision.pipeline import Pipeline


def test_health_reports_camera_and_fps():
    pipeline = Pipeline(FakeCamera(fps=60), [])
    with TestClient(create_app(pipeline)) as client:
        pipeline.wait_for_jpeg(after=0, timeout=2)
        body = client.get("/health").json()
    assert body["camera_open"] is True
    assert "fps" in body
    assert body["stages"] == {}


def test_mjpeg_parts_yields_jpeg_chunks():
    pipeline = Pipeline(FakeCamera(fps=60), [])
    pipeline.start()
    try:
        parts = list(mjpeg_parts(pipeline, max_frames=3))
    finally:
        pipeline.stop()
    assert len(parts) == 3
    for part in parts:
        assert part.startswith(b"--frame\r\nContent-Type: image/jpeg")
        assert b"\xff\xd8" in part  # JPEG start marker
