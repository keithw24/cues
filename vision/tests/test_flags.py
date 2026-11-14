import pytest

from vision import flags

REGISTRY = {
    "vision.on_feature": {"description": "x", "default": True, "owner": "k", "ticket": "T0"},
    "vision.off_feature": {"description": "x", "default": False, "owner": "k", "ticket": "T0"},
    "web.other": {"description": "x", "default": True, "owner": "e", "ticket": "W0"},
}


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch):
    monkeypatch.setattr(flags, "load_registry", lambda: REGISTRY)


def test_env_name():
    assert flags.env_name("vision.supabase_events") == "CUES_FLAG_VISION_SUPABASE_EVENTS"


def test_default_from_registry():
    assert flags.enabled("vision.on_feature", env={}) is True
    assert flags.enabled("vision.off_feature", env={}) is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("0", False),
        ("false", False),
        (" False ", False),
    ],
)
def test_env_override(raw, expected):
    env = {"CUES_FLAG_VISION_OFF_FEATURE": raw, "CUES_FLAG_VISION_ON_FEATURE": raw}
    assert flags.enabled("vision.off_feature", env=env) is expected
    assert flags.enabled("vision.on_feature", env=env) is expected


def test_empty_env_value_uses_default():
    assert flags.enabled("vision.on_feature", env={"CUES_FLAG_VISION_ON_FEATURE": ""}) is True


def test_invalid_value_is_an_error():
    with pytest.raises(flags.InvalidFlagValueError):
        flags.enabled("vision.on_feature", env={"CUES_FLAG_VISION_ON_FEATURE": "yes"})


def test_unknown_flag_is_an_error():
    with pytest.raises(flags.UnknownFlagError):
        flags.enabled("vision.typo", env={})


def test_reads_process_environment(monkeypatch):
    monkeypatch.setenv("CUES_FLAG_VISION_OFF_FEATURE", "1")
    assert flags.enabled("vision.off_feature") is True


def test_snapshot_lists_only_vision_flags():
    assert flags.snapshot(env={}) == {"vision.off_feature": False, "vision.on_feature": True}


def test_real_registry_flags_all_resolve(monkeypatch):
    monkeypatch.undo()  # use the real flags.json
    flags.load_registry.cache_clear()
    for name in flags.load_registry():
        if name.startswith("vision."):
            assert isinstance(flags.enabled(name, env={}), bool)
