"""One camera per station.

Seat rows are named by station and person number (S1-P1), so two cameras working for the
same station overwrite each other's rows and appear as phantom people. Each camera process
claims its station with a random writer id (a lease the database enforces, migration 1700).
While another camera holds a fresh lease this one is refused: it pauses (reads nothing,
writes nothing), keeps retrying, and takes over when the other camera stops (it releases at
once) or crashes (its lease expires after TTL_SECONDS).

The claim itself is part of the station tick (session_sync): this module holds the writer id,
interprets the tick's answer and releases the lease. Only a random id and a station name are
sent; no frames, scores or identities.
"""

from __future__ import annotations

import logging
import threading
import uuid

log = logging.getLogger(__name__)

TTL_SECONDS = 10  # a crashed camera's lease expires after this long


class LeaseStatus:
    """What the rest of the service can ask: is this camera being refused right now?"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refused = False
        self._held_seconds_ago: float | None = None

    def set(self, refused: bool, held_seconds_ago: float | None = None) -> None:
        with self._lock:
            self._refused = refused
            self._held_seconds_ago = held_seconds_ago if refused else None

    @property
    def refused(self) -> bool:
        with self._lock:
            return self._refused

    def snapshot(self) -> dict:
        with self._lock:
            return {"refused": self._refused, "held_seconds_ago": self._held_seconds_ago}


STATUS = LeaseStatus()


class StationLease:
    """This process's claim on a station. A new random id on every start."""

    def __init__(self, client, status: LeaseStatus = STATUS, ttl: int = TTL_SECONDS) -> None:
        self.client = client
        self.status = status
        self.ttl = ttl
        self.writer_id = uuid.uuid4()
        self._warned_refused = False

    def apply(self, station_id: str, tick: dict) -> bool:
        """Record the answer to a station tick. True when this camera may use the station."""
        if tick.get("granted"):
            if self._warned_refused:
                log.info("station %s: this camera now holds it", station_id)
            self._warned_refused = False
            self.status.set(False)
            return True
        held = tick.get("held_seconds_ago")
        self.status.set(True, held if isinstance(held, (int, float)) else None)
        if not self._warned_refused:
            log.warning(
                "station %s is in use by another camera; this one is paused until it stops",
                station_id,
            )
            self._warned_refused = True
        return False

    def release(self, station_id: str | None) -> None:
        """Hand the station over at once (best effort: the lease expires anyway)."""
        if not station_id:
            return
        try:
            self.client.rpc(
                "release_station_writer",
                {"p_station_id": station_id, "p_writer_id": str(self.writer_id)},
            ).execute()
        except Exception:
            pass
        self.status.set(False)
