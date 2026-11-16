"""Teacher "Mark as reviewed" marks, so vision can put a child back to working.

When a teacher marks a flagged child as reviewed in the dashboard, the database records a
mark (table seat_review_marks, migration 1500). The station tick (session_sync) returns the
current session's marks and stores them here so the status stage can restart that child's
timers: status back to in_progress, and the no-progress and review timers start again.

Only a seat id and a timestamp are read. Vision never writes marks and reads no frames
or images from them.
"""

from __future__ import annotations

import threading
from datetime import datetime


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ReviewMarks:
    """Thread-safe latest mark per (session, seat); written by the station tick, read per frame."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._marks: dict[tuple[str, str], datetime] = {}

    def replace(self, session_id: str, marks: dict[str, datetime]) -> None:
        """Make `marks` the full set for this session (and forget other sessions')."""
        with self._lock:
            self._marks = {(session_id, seat): at for seat, at in marks.items()}

    def get(self, session_id, seat_id: str) -> datetime | None:
        with self._lock:
            return self._marks.get((str(session_id), seat_id))

    def clear(self) -> None:
        with self._lock:
            self._marks = {}


MARKS = ReviewMarks()
