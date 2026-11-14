import numpy as np
import pytest
from fastapi.testclient import TestClient

from vision import activities
from vision.app import create_app
from vision.camera import FakeCamera
from vision.gestures import templates as tpl
from vision.pipeline import Pipeline


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(activities, "CUSTOM_FILE", tmp_path / "custom_gestures.catalog.json")
    monkeypatch.setattr(tpl, "TEMPLATES_DIR", tmp_path)
    activities.load_activities.cache_clear()
    yield tmp_path
    activities.load_activities.cache_clear()


def client(monkeypatch, on: bool):
    monkeypatch.setenv("CUES_FLAG_VISION_CUSTOM_GESTURES", "1" if on else "0")
    monkeypatch.setenv("CUES_FLAG_VISION_GESTURES", "1")
    return TestClient(create_app(Pipeline(FakeCamera(fps=30), [])))


def test_create_list_and_delete(local_store, monkeypatch):
    with client(monkeypatch, True) as c:
        r = c.post("/gestures", json={"name": "Wave hello"})
        assert r.status_code == 201
        g = r.json()
        assert g["id"] == "custom_wave_hello" and g["custom"] and not g["ready"]
        assert c.post("/gestures", json={"name": "Wave hello"}).json()["id"] == (
            "custom_wave_hello_2"
        )
        assert activities.get("custom_wave_hello").success_threshold == 0.78

        t = tpl.Templates("custom_wave_hello")
        t.add("target", [np.zeros(63)])
        tpl.save(t)
        listed = {x["id"]: x for x in c.get("/gestures").json()}
        assert listed["custom_wave_hello"]["ready"] is True
        assert listed["thumbs_up"]["builtin"] is True

        assert c.delete("/gestures/custom_wave_hello").json() == {"deleted": True}
        assert not (local_store / "custom_wave_hello.json").exists()
        assert c.delete("/gestures/thumbs_up").status_code == 404
        assert "custom_wave_hello" not in activities.load_activities()


def test_bad_name_is_rejected(local_store, monkeypatch):
    with client(monkeypatch, True) as c:
        assert c.post("/gestures", json={"name": "!!!"}).status_code == 422


def test_new_gesture_is_detected_without_restart(local_store):
    from vision.stages.s46_recognize import RecognizeStage

    stage = RecognizeStage()
    assert "custom_wave" not in stage.gesture_ids
    activities.add_custom_gesture("Wave")
    assert "custom_wave" in stage.gesture_ids


def test_flag_off_service_still_works(local_store, monkeypatch):
    with client(monkeypatch, False) as c:
        assert c.post("/gestures", json={"name": "Wave"}).status_code in (404, 405)
        assert c.get("/health").status_code == 200


def test_dashboard_origin_allowed(local_store, monkeypatch):
    with client(monkeypatch, True) as c:
        r = c.options(
            "/gestures",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
        r = c.get("/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in r.headers
