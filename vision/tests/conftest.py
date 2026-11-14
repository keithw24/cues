import os

import pytest


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
