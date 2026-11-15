"""Activities (tasks) and the current task for each seat.

Until the app's `activities` table and current-task sync are connected, the
vision service reads vision/activities.json (same shape as notes/archive/TEAM_WORKFLOW.md
§3.4) and takes the current task from CUES_TASK (default: thumbs_up).

Thresholds are per activity; there is no single threshold for every task.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ACTIVITIES_FILE = Path(__file__).resolve().parent / "activities.json"
# Gestures a teacher created from the dashboard. Stored next to their recorded
# examples in vision/templates/ (git-ignored, never leaves this laptop). The dots
# in the name keep it apart from any <activity_id>.json example file.
CUSTOM_FILE = ACTIVITIES_FILE.parent / "templates" / "custom_gestures.catalog.json"
CUSTOM_PREFIX = "custom_"
CUSTOM_SUCCESS, CUSTOM_REVIEW = 0.78, 0.58
# A gesture task flags a person (Needs Review) after this much time on task without
# any score reaching the review band. Rule tasks (raise hand) keep their own, longer wait.
# CUES_GESTURE_NO_PROGRESS_SECONDS changes it for every gesture, built-in and recorded
# (for example 30 to go back to the old wait without a code change).
GESTURE_NO_PROGRESS_SECONDS = 3


def _gesture_wait() -> int:
    raw = os.environ.get("CUES_GESTURE_NO_PROGRESS_SECONDS", "").strip()
    try:
        seconds = int(raw)
    except ValueError:
        return GESTURE_NO_PROGRESS_SECONDS
    return seconds if seconds > 0 else GESTURE_NO_PROGRESS_SECONDS


_custom_lock = threading.Lock()


@dataclass(frozen=True)
class Activity:
    id: str
    name: str
    check_type: str  # "gesture" or "rule"
    success_threshold: float
    review_threshold: float
    no_progress_seconds: int
    keywords: tuple[str, ...] = ()
    # MediaPipe Gesture Recognizer label (e.g. "Thumb_Up") for built-in gestures.
    # None = a teacher-recorded gesture, matched against recorded examples.
    builtin: str | None = None


def _no_progress_override() -> int | None:
    """CUES_NO_PROGRESS_SECONDS: shorten the "no progress" wait for every task (demo mode).

    The demo launcher sets it so vision's Needs Review status arrives about when the
    agent's accelerated review request does. It only ever shortens a wait: a task whose
    own wait is already shorter (gestures, 3s) keeps it. Unset, empty or invalid: no override.
    """
    raw = os.environ.get("CUES_NO_PROGRESS_SECONDS", "").strip()
    if not raw:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


@lru_cache(maxsize=1)
def load_activities(path: Path = ACTIVITIES_FILE) -> dict[str, Activity]:
    items = json.loads(Path(path).read_text()) + _read_custom()
    override = _no_progress_override()
    gesture_wait = _gesture_wait()
    result = {}
    for item in items:
        activity = Activity(
            id=item["id"],
            name=item["name"],
            check_type=item["check_type"],
            success_threshold=float(item["success_threshold"]),
            review_threshold=float(item["review_threshold"]),
            no_progress_seconds=_wait(item, gesture_wait, override),
            keywords=tuple(item.get("keywords", [])),
            builtin=item.get("builtin"),
        )
        if activity.check_type not in ("gesture", "rule"):
            raise ValueError(f"{activity.id}: unknown check_type {activity.check_type!r}")
        if not 0 <= activity.review_threshold <= activity.success_threshold <= 1:
            raise ValueError(f"{activity.id}: need 0 <= review <= success <= 1")
        result[activity.id] = activity
    return result


def _wait(item: dict, gesture_wait: int, override: int | None) -> int:
    """Every gesture (including one recorded before this default) uses the gesture
    wait; a rule task keeps its own. CUES_NO_PROGRESS_SECONDS only ever shortens."""
    base = gesture_wait if item["check_type"] == "gesture" else int(item["no_progress_seconds"])
    return min(base, override) if override else base


def _read_custom() -> list[dict]:
    if not CUSTOM_FILE.exists():
        return []
    return json.loads(CUSTOM_FILE.read_text())


def _write_custom(items: list[dict]) -> None:
    CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2))
    tmp.replace(CUSTOM_FILE)
    load_activities.cache_clear()


def is_custom(activity_id: str) -> bool:
    return any(item["id"] == activity_id for item in _read_custom())


def _slug(name: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in name.strip().lower())
    return "_".join(p for p in out.split("_") if p)[:40]


def add_custom_gesture(name: str, keywords: tuple[str, ...] = ()) -> Activity:
    """Create a teacher-recorded gesture task. Returns it; record examples next."""
    slug = _slug(name)
    if not slug:
        raise ValueError("name needs at least one letter or digit")
    with _custom_lock:
        taken = set(load_activities())
        aid, n = f"{CUSTOM_PREFIX}{slug}", 2
        while aid in taken:
            aid, n = f"{CUSTOM_PREFIX}{slug}_{n}", n + 1
        item = {
            "id": aid,
            "name": name.strip(),
            "check_type": "gesture",
            "keywords": list(keywords) or [name.strip().lower()],
            "success_threshold": CUSTOM_SUCCESS,
            "review_threshold": CUSTOM_REVIEW,
            "no_progress_seconds": GESTURE_NO_PROGRESS_SECONDS,
        }
        _write_custom(_read_custom() + [item])
    return get(aid)


def remove_custom_gesture(activity_id: str) -> bool:
    """Remove a dashboard-created gesture. Built-in catalog entries can't be removed."""
    with _custom_lock:
        items = _read_custom()
        kept = [i for i in items if i["id"] != activity_id]
        if len(kept) == len(items):
            return False
        _write_custom(kept)
    return True


def get(activity_id: str) -> Activity:
    activities = load_activities()
    if activity_id not in activities:
        raise KeyError(f"unknown activity {activity_id!r}; known: {sorted(activities)}")
    return activities[activity_id]


class CurrentTasks:
    """Class-wide current task plus optional per-seat overrides."""

    def __init__(self, default: str) -> None:
        get(default)
        self._lock = threading.Lock()
        self.default = default
        self.class_task = default
        self.overrides: dict[str, str] = {}

    def reset(self) -> None:
        """Back to the start-up task with no overrides (used on a station change)."""
        with self._lock:
            self.class_task = self.default
            self.overrides.clear()

    def for_seat(self, seat_id: str) -> str:
        with self._lock:
            return self.overrides.get(seat_id, self.class_task)

    def set_class_task(self, activity_id: str) -> None:
        get(activity_id)
        with self._lock:
            self.class_task = activity_id

    def set_override(self, seat_id: str, activity_id: str | None) -> None:
        if activity_id is not None:
            get(activity_id)
        with self._lock:
            if activity_id is None:
                self.overrides.pop(seat_id, None)
            else:
                self.overrides[seat_id] = activity_id


TASKS = CurrentTasks(os.environ.get("CUES_TASK", "thumbs_up"))
