"""How much the overlay draws on the video.

CUES_OVERLAY=simple (default): in people mode, one box and one label per
person: id, task and score on the first line; status, latest event and top
expression on the second. Hands are shown as small dots. Nothing else.

CUES_OVERLAY=debug: everything each stage can draw (hand skeletons, face
boxes, expression labels, raise-hand reference lines). `vision.watch --debug`
turns this on.

Seats mode keeps its own per-seat labels in both levels.
"""

from __future__ import annotations

import os


def debug() -> bool:
    return os.environ.get("CUES_OVERLAY", "simple").lower() == "debug"
