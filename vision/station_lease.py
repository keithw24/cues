"""One camera per station.

Seat rows are named by station and person number (S1-P1), so two cameras working for the
same station overwrite each other's rows and appear as phantom people. Each camera process
claims its station with a random writer id (a lease the database enforces, migration 1700).
While another camera holds a fresh lease this one is refused: it pauses (reads nothing,
writes nothing), keeps retrying about once a second, and takes over when the other camera
stops (it releases at once) or crashes (its lease expires after TTL_SECONDS).

Only a random id and a station name are sent; no frames, scores or identities.
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


def _function_missing(error: Exception) -> bool:
    """The database function is not there yet (migration 1700 not applied)."""
    code = getattr(error, "code", None)
    message = str(error)
    return code in ("PGRST202", "42883") or "Could not find the function" in message


class StationLease:
    """This process's claim on a station. A new random id on every start."""

    def __init__(self, client, status: LeaseStatus = STATUS, ttl: int = TTL_SECONDS) -> None:
        self.client = client
        self.status = status
        self.ttl = ttl
        self.writer_id = uuid.uuid4()
        self._warned_refused = False
        self._warned_missing = False

    def claim(self, station_id: str) -> bool:
        """True when this camera may use the station. Network errors propagate (the caller
        treats them like any failed sync: paused, retried)."""
        try:
            data = (
                self.client.rpc(
                    "claim_station_writer",
                    {
                        "p_station_id": station_id,
                        "p_writer_id": str(self.writer_id),
                        "p_ttl_seconds": self.ttl,
                    },
                )
                .execute()
                .data
            )
        except Exception as error:
            if _function_missing(error):
                # Migration 1700 is not applied: do not stop working, but say so once.
                if not self._warned_missing:
                    log.warning("one-camera-per-station guard unavailable: apply migration 1700")
                    self._warned_missing = True
                self.status.set(False)
                return True
            raise
        granted = bool(isinstance(data, dict) and data.get("granted"))
        if granted:
            if self._warned_refused:
                log.info("station %s: this camera now holds it", station_id)
            self._warned_refused = False
            self.status.set(False)
            return True
        held = data.get("held_seconds_ago") if isinstance(data, dict) else None
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
