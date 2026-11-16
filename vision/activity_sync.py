"""Teacher task synchronization via Supabase.

With vision.session_lifecycle on, the station follows authoritative session
UUID/activity/revision, acknowledges configuration and pauses task processing
on end or sync failure. The implementation
below is the preserved legacy path when the lifecycle flag is off.

The teacher picks a task on Evan's dashboard. The dashboard
saves it through station-scoped session RPCs. This module checks that row
every POLL_SECONDS and sets the class-wide task in vision.activities.TASKS.

* Off unless the `vision.activity_sync` flag is on and Supabase keys are set.
  When it is off, the task comes from CUES_TASK as before.
* The session is CUES_SESSION_ID (the same id vision writes into events).
* An activity id that vision does not know is ignored, with a warning.
* Network errors are logged and retried on the next check; the camera loop is
  never blocked.

Polling (not Supabase Realtime) keeps this simple and robust: one small query
per second, on a background thread.
"""

from __future__ import annotations

import logging
import os
import threading

from vision import activities
from vision.activities import TASKS

POLL_SECONDS = 1.0

log = logging.getLogger(__name__)


class ActivitySync:
    def __init__(
        self,
        client,
        session_id: str,
        tasks=TASKS,
        poll_seconds: float = POLL_SECONDS,
        station=None,
    ):
        from vision import station as station_module

        self.client = client
        self.session_id = session_id
        self.tasks = tasks
        self.station = station or station_module.STATION
        self._generation = self.station.generation
        self.poll_seconds = poll_seconds
        self.last_seen: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check_once(self) -> str | None:
        """Read the session's current activity and apply it. Returns the id applied."""
        station_id, generation = self.station.snapshot()
        if generation != self._generation:
            self._generation = generation
            self.last_seen = None  # TASKS was reset for the new station; apply again
        if station_id is None:
            return None  # no teacher station yet
        rows = (
            self.client.table("sessions")
            .select("current_activity_id,station_id")
            .eq("id", self.session_id)
            .limit(1)
            .execute()
            .data
        )
        row_station = rows[0].get("station_id") if rows else None
        if row_station is not None and row_station != station_id:
            # CUES_SESSION_ID belongs to another teacher's station: never follow it.
            log.warning(
                "session %s belongs to station %s, not %s; ignored",
                self.session_id,
                row_station,
                station_id,
            )
            return None
        activity_id = rows[0].get("current_activity_id") if rows else None
        if not activity_id or activity_id == self.last_seen:
            return None
        self.last_seen = activity_id
        try:
            activities.get(activity_id)
        except KeyError:
            log.warning("session task %r is not in vision/activities.json; ignored", activity_id)
            return None
        self.tasks.set_class_task(activity_id)
        log.info("current task from the app: %s", activity_id)
        return activity_id

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="activity-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as exc:  # network or permission problems: try again later
                log.warning("could not read the current task: %s", exc)
            self._stop.wait(self.poll_seconds)


def sync_from_env():
    """Station lifecycle takes precedence; otherwise preserve legacy fixed-session sync."""
    from vision import flags
    from vision.supabase_client import get_client

    if flags.enabled("vision.session_lifecycle"):
        from vision.session_sync import STATION_SESSION, StationSessionSync

        STATION_SESSION.invalidate()
        client = get_client()
        if client is None:
            log.warning("session lifecycle enabled without station credentials; tasks stay paused")
            return None
        from vision.station_lease import StationLease

        # Follows vision.station.STATION; one camera per station (the lease).
        return StationSessionSync(client, lease=StationLease(client))
    if not flags.enabled("vision.activity_sync"):
        return None
    client = get_client()
    session_id = os.environ.get("CUES_SESSION_ID")
    if client is None or not session_id:
        # Fail loudly: otherwise the teacher's task buttons silently do nothing.
        raise RuntimeError(
            "vision.activity_sync is on but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY or "
            "CUES_SESSION_ID is missing from .env. Set them, or turn the flag off."
        )
    log.info("current task follows session %s", session_id)
    return ActivitySync(client, session_id)
