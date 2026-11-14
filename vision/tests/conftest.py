import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip tests marked `hardware` unless CUES_HARDWARE=1.

    CI has no camera and does not download model weights, so these tests only
    run on a developer laptop: `CUES_HARDWARE=1 uv run pytest`.
    """
    if os.environ.get("CUES_HARDWARE") == "1":
        return
    skip = pytest.mark.skip(reason="hardware test; set CUES_HARDWARE=1 to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)
