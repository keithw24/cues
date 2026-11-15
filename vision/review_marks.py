"""Teacher "Mark as reviewed" marks, so vision can put a child back to working.

When a teacher marks a flagged child as reviewed in the dashboard, the database records a
mark (table seat_review_marks, migration 1500). This module reads those marks for the
current session so the status stage can restart that child's timers: status back to
in_progress, and the no-progress and review timers start again.

Only a seat id and a timestamp are read. Vision never writes marks and reads no frames
or images from them.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

log = logging.getLogger(__name__)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ReviewMarks:
    """Thread-safe latest mark per (session, seat); written by the poller, read per frame."""

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


class ReviewMarkSync:
    """Polls the current station session's marks once a second."""

    def __init__(self, client, station=None, marks: ReviewMarks = MARKS, poll_seconds=1.0) -> None:
        from vision import station as station_module

        self.client = client
        self.station = station or station_module.STATION
        self.marks = marks
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failing = False

    def check_once(self) -> None:
        station_id = self.station.get()
        if not station_id:
            self.marks.clear()  # no teacher station yet
            return
        sessions = (
            self.client.table("sessions")
            .select("id")
            .eq("station_id", station_id)
            .is_("ended_at", "null")
            .execute()
            .data
            or []
        )
        if len(sessions) != 1:
            self.marks.clear()
            return
        session_id = str(sessions[0]["id"])
        rows = (
            self.client.table("seat_review_marks")
            .select("seat_id,marked_at")
            .eq("session_id", session_id)
            .execute()
            .data
            or []
        )
        if self.station.get() != station_id:
            return  # the station changed while we were reading: drop this answer
        self.marks.replace(session_id, {r["seat_id"]: parse_time(r["marked_at"]) for r in rows})

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="review-marks-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
                self._failing = False
            except Exception as error:
                # Keep the marks we have; log once per outage (for example migration 1500
                # not applied yet), not once a second.
                if not self._failing:
                    log.warning(
                        "review marks unavailable (%s); will keep trying", type(error).__name__
                    )
                self._failing = True
            self._stop.wait(self.poll_seconds)


def sync_from_env() -> ReviewMarkSync | None:
    from vision import flags
    from vision.supabase_client import get_client

    if not flags.enabled("vision.review_marks"):
        return None
    client = get_client()
    if client is None:
        return None  # offline: there is no teacher dashboard to mark anything
    return ReviewMarkSync(client)
