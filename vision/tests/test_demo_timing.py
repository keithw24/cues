"""Demo mode: vision's "no progress" wait matches the agent's accelerated review."""

import pytest

from vision import activities


@pytest.fixture(autouse=True)
def fresh_catalog(monkeypatch, tmp_path):
    # Never read this laptop's own recorded gestures (git-ignored).
    monkeypatch.setattr(activities, "CUSTOM_FILE", tmp_path / "custom_gestures.catalog.json")
    monkeypatch.delenv("CUES_GESTURE_NO_PROGRESS_SECONDS", raising=False)
    activities.load_activities.cache_clear()
    yield
    activities.load_activities.cache_clear()


def waits():
    return {(a.check_type, a.no_progress_seconds) for a in activities.load_activities().values()}


def test_default_wait_flags_a_gesture_after_three_seconds(monkeypatch):
    monkeypatch.delenv("CUES_NO_PROGRESS_SECONDS", raising=False)
    assert waits() == {("gesture", activities.GESTURE_NO_PROGRESS_SECONDS), ("rule", 30)}
    assert activities.GESTURE_NO_PROGRESS_SECONDS == 3


def test_override_only_shortens(monkeypatch):
    monkeypatch.setenv("CUES_NO_PROGRESS_SECONDS", "4")
    # Raise hand drops to 4s; gestures keep their shorter 3s.
    assert waits() == {("gesture", 3), ("rule", 4)}
    monkeypatch.setenv("CUES_NO_PROGRESS_SECONDS", "2")
    activities.load_activities.cache_clear()
    assert waits() == {("gesture", 2), ("rule", 2)}


@pytest.mark.parametrize("bad", ["", "  ", "abc", "0", "-3", "2.5"])
def test_invalid_override_is_ignored(monkeypatch, bad):
    monkeypatch.setenv("CUES_NO_PROGRESS_SECONDS", bad)
    assert waits() == {("gesture", 3), ("rule", 30)}


def test_demo_launcher_uses_the_agents_demo_stall_time():
    from agent.escalation import DEMO_ESCALATION_CONFIG

    source = open("agent/dev.py").read()
    assert "CUES_NO_PROGRESS_SECONDS" in source
    assert "DEMO_ESCALATION_CONFIG.normal_stall_seconds" in source
    assert DEMO_ESCALATION_CONFIG.normal_stall_seconds < 30


def test_one_setting_changes_every_gesture_and_old_recordings_follow_it(monkeypatch, tmp_path):
    import json

    stored = tmp_path / "custom_gestures.catalog.json"
    stored.write_text(
        json.dumps(
            [
                {
                    "id": "custom_old",
                    "name": "Old",
                    "check_type": "gesture",
                    "keywords": ["old"],
                    "success_threshold": 0.78,
                    "review_threshold": 0.58,
                    "no_progress_seconds": 30,  # recorded before the 3s default
                }
            ]
        )
    )
    monkeypatch.setattr(activities, "CUSTOM_FILE", stored)
    monkeypatch.delenv("CUES_NO_PROGRESS_SECONDS", raising=False)
    activities.load_activities.cache_clear()
    assert activities.get("custom_old").no_progress_seconds == 3
    monkeypatch.setenv("CUES_GESTURE_NO_PROGRESS_SECONDS", "30")  # the way back
    activities.load_activities.cache_clear()
    assert waits() == {("gesture", 30), ("rule", 30)}
    monkeypatch.setenv("CUES_GESTURE_NO_PROGRESS_SECONDS", "nonsense")
    activities.load_activities.cache_clear()
    assert waits() == {("gesture", 3), ("rule", 30)}


def test_a_new_recorded_gesture_gets_the_gesture_wait(monkeypatch, tmp_path):
    monkeypatch.delenv("CUES_NO_PROGRESS_SECONDS", raising=False)
    assert activities.add_custom_gesture("Wave").no_progress_seconds == 3
