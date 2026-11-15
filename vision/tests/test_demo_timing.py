"""Demo mode: vision's "no progress" wait matches the agent's accelerated review."""

import pytest

from vision import activities


@pytest.fixture(autouse=True)
def fresh_catalog():
    activities.load_activities.cache_clear()
    yield
    activities.load_activities.cache_clear()


def test_default_wait_is_unchanged(monkeypatch):
    monkeypatch.delenv("CUES_NO_PROGRESS_SECONDS", raising=False)
    assert {a.no_progress_seconds for a in activities.load_activities().values()} == {30}


def test_override_shortens_every_task(monkeypatch):
    monkeypatch.setenv("CUES_NO_PROGRESS_SECONDS", "4")
    waits = {a.no_progress_seconds for a in activities.load_activities().values()}
    assert waits == {4}


@pytest.mark.parametrize("bad", ["", "  ", "abc", "0", "-3", "2.5"])
def test_invalid_override_is_ignored(monkeypatch, bad):
    monkeypatch.setenv("CUES_NO_PROGRESS_SECONDS", bad)
    assert {a.no_progress_seconds for a in activities.load_activities().values()} == {30}


def test_demo_launcher_uses_the_agents_demo_stall_time():
    from agent.escalation import DEMO_ESCALATION_CONFIG

    source = open("agent/dev.py").read()
    assert "CUES_NO_PROGRESS_SECONDS" in source
    assert "DEMO_ESCALATION_CONFIG.normal_stall_seconds" in source
    assert DEMO_ESCALATION_CONFIG.normal_stall_seconds < 30
