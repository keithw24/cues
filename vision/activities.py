"""Activities (tasks) and the current task for each seat.

Until the app's `activities` table and current-task sync are connected, the
vision service reads vision/activities.json (same shape as TEAM_WORKFLOW.md
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


@dataclass(frozen=True)
class Activity:
    id: str
    name: str
    check_type: str  # "gesture" or "rule"
    success_threshold: float
    review_threshold: float
    no_progress_seconds: int
    keywords: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def load_activities(path: Path = ACTIVITIES_FILE) -> dict[str, Activity]:
    items = json.loads(Path(path).read_text())
    result = {}
    for item in items:
        activity = Activity(
            id=item["id"],
            name=item["name"],
            check_type=item["check_type"],
            success_threshold=float(item["success_threshold"]),
            review_threshold=float(item["review_threshold"]),
            no_progress_seconds=int(item["no_progress_seconds"]),
            keywords=tuple(item.get("keywords", [])),
        )
        if activity.check_type not in ("gesture", "rule"):
            raise ValueError(f"{activity.id}: unknown check_type {activity.check_type!r}")
        if not 0 <= activity.review_threshold <= activity.success_threshold <= 1:
            raise ValueError(f"{activity.id}: need 0 <= review <= success <= 1")
        result[activity.id] = activity
    return result


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
        self.class_task = default
        self.overrides: dict[str, str] = {}

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
