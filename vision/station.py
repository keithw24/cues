"""Which station this laptop's vision service works for.

Normal use: the service starts with no station. The signed-in teacher's
dashboard resolves the teacher's station and sends it to this laptop's
vision service (POST http://127.0.0.1:8000/config, vision/routes/station.py).
Until then vision tracks people for the local video but writes nothing and
follows no session.

* `CUES_STATION_ID` pins the station for development and tests. The dashboard
  may then only confirm that same station; a different one is refused.
* With the `vision.station_config` flag off, the station is `S1` as before
  (or `CUES_STATION_ID`), and /config is not served.

Changing the station calls every subscriber (session cache, current tasks),
and the stages compare `generation` each frame to drop their own state, so
no task score, tracking, activity or session id carries over to another
station.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable, Mapping

log = logging.getLogger(__name__)

# 1-64 letters, digits, "_" or "-": the same rule as web/lib/default-station.ts.
# Seat ids are "<station>-P<n>", so no spaces or other symbols.
STATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
LEGACY_STATION = "S1"
# Track ids before any station is set. Never written to Supabase.
UNCONFIGURED_PREFIX = "local"


class InvalidStationError(ValueError):
    """The station id does not match STATION_ID_PATTERN."""


class StationPinnedError(RuntimeError):
    """CUES_STATION_ID pins another station on this laptop."""


def validate(station_id: object) -> str:
    if not isinstance(station_id, str) or not STATION_ID_PATTERN.fullmatch(station_id):
        raise InvalidStationError("station_id must be 1-64 letters, digits, '_' or '-'")
    return station_id


class ActiveStation:
    """Thread-safe current station. `generation` increases on every change."""

    def __init__(self, station_id: str | None = None, pinned: bool = False) -> None:
        self._lock = threading.Lock()
        self._station = validate(station_id) if station_id is not None else None
        self._generation = 0
        self.pinned = pinned
        self._listeners: list[Callable[[str | None, str], None]] = []

    def get(self) -> str | None:
        with self._lock:
            return self._station

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def snapshot(self) -> tuple[str | None, int]:
        with self._lock:
            return self._station, self._generation

    def subscribe(self, listener: Callable[[str | None, str], None]) -> None:
        """listener(old, new) runs after each change, on the caller's thread."""
        with self._lock:
            self._listeners.append(listener)

    def set(self, station_id: object, *, allow_clear: bool = False) -> bool:
        """Set the station. Returns False if it was already this station (no reset)."""
        new = None if station_id is None and allow_clear else validate(station_id)
        with self._lock:
            old = self._station
            if new == old:
                return False
            if self.pinned:
                raise StationPinnedError(
                    f"CUES_STATION_ID pins this laptop to {old}; unset it to follow the dashboard"
                )
            self._station = new
            self._generation += 1
            listeners = list(self._listeners)
        log.info("station changed: %s -> %s", old or "(none)", new)
        for listener in listeners:
            try:
                listener(old, new)
            except Exception:
                log.exception("station change listener failed")
        return True


def from_env(env: Mapping[str, str] | None = None) -> ActiveStation:
    env = os.environ if env is None else env
    override = env.get("CUES_STATION_ID", "").strip()
    if override:
        log.info("station pinned by CUES_STATION_ID=%s (dev/test override)", override)
        return ActiveStation(override, pinned=True)
    if env is os.environ:
        from vision.supabase_client import online  # also loads the root .env

        if not online():
            return ActiveStation(LEGACY_STATION)  # offline: one fixed station, no dashboard
    elif not (env.get("SUPABASE_URL") and env.get("SUPABASE_SERVICE_ROLE_KEY")):
        return ActiveStation(LEGACY_STATION)
    return ActiveStation(None)


STATION = from_env()


def _reset_shared_state(old: str | None, new: str) -> None:
    """Session lease and current tasks belong to one station only."""
    from vision.activities import TASKS
    from vision.session_sync import STATION_SESSION

    STATION_SESSION.invalidate()
    TASKS.reset()


STATION.subscribe(_reset_shared_state)
