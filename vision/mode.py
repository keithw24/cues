"""Which mode the vision service runs in.

CUES_MODE=task (default): each person has one assigned task (from the
dashboard, CUES_TASK or --task); that task's score drives seat_state, status
and events.

CUES_MODE=recognize: vision also works out which gesture each person is doing,
from RECOGNIZE_SET, and shows it on the overlay and in vision.watch. This is
display-only for now: seat_state, status and events still follow the assigned
task, so nothing sent to Supabase changes.
"""

from __future__ import annotations

import os

MODES = ("task", "recognize")

# Gestures recognise mode chooses between. Add more ids here later
# (any activity in vision/activities.json).
RECOGNIZE_SET = ("thumbs_up", "raise_hand")


def current() -> str:
    mode = os.environ.get("CUES_MODE", "task").strip().lower()
    if mode not in MODES:
        raise ValueError(f"CUES_MODE must be one of {MODES}, got {mode!r}")
    return mode


def recognizing() -> bool:
    return current() == "recognize"
