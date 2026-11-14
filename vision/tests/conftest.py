import os

import pytest

# vision.supabase_client loads the developer's root .env into os.environ when it is
# imported. Tests must not depend on a laptop's own settings (flags, session id) or
# reach its real Supabase project, so anything that import adds is removed again.
_before = set(os.environ)
import vision.supabase_client  # noqa: E402,F401

for _key in set(os.environ) - _before:
    del os.environ[_key]


@pytest.fixture(autouse=True)
def _isolated_gesture_catalog(tmp_path, monkeypatch):
    """Ignore gestures a teacher created on this laptop (vision/templates/)."""
    from vision import activities

    monkeypatch.setattr(activities, "CUSTOM_FILE", tmp_path / "custom.catalog.json")
    activities.load_activities.cache_clear()
    yield
    activities.load_activities.cache_clear()


def pytest_collection_modifyitems(config, items):
    """Skip tests marked `hardware` unless CUES_HARDWARE=1.

    CI has no camera and does not download model weights, so these tests only
    run on a developer laptop: `CUES_HARDWARE=1 uv run pytest vision`.
    """
    if os.environ.get("CUES_HARDWARE") == "1":
        return
    skip = pytest.mark.skip(reason="hardware test; set CUES_HARDWARE=1 to run")
    for item in items:
        # get_closest_marker matches only the real marker, not folder, module
        # or class names that happen to contain "hardware".
        if item.get_closest_marker("hardware") is not None:
            item.add_marker(skip)
