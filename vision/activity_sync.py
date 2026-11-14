"""Current task from the app: reads sessions.current_activity_id from Supabase.

The teacher picks a task on Evan's dashboard (buttons or voice). The dashboard
writes it to the `sessions` row for this session. This module checks that row
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
    def __init__(self, client, session_id: str, tasks=TASKS, poll_seconds: float = POLL_SECONDS):
        self.client = client
        self.session_id = session_id
        self.tasks = tasks
        self.poll_seconds = poll_seconds
        self.last_seen: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check_once(self) -> str | None:
        """Read the session's current activity and apply it. Returns the id applied."""
        rows = (
            self.client.table("sessions")
            .select("current_activity_id")
            .eq("id", self.session_id)
            .limit(1)
            .execute()
            .data
        )
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


def sync_from_env() -> ActivitySync | None:
    """An ActivitySync if the flag is on, keys are set and CUES_SESSION_ID is given."""
    from vision import flags
    from vision.supabase_client import get_client

    if not flags.enabled("vision.activity_sync"):
        return None
    client = get_client()
    session_id = os.environ.get("CUES_SESSION_ID")
    if client is None or not session_id:
        log.warning("vision.activity_sync is on but Supabase keys or CUES_SESSION_ID are missing")
        return None
    return ActivitySync(client, session_id)
