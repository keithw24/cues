"""Follow teacher-managed station sessions. Camera data never enters this module."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from shared.contracts import Session
from vision import activities

log = logging.getLogger(__name__)
# How long a confirmed session stays usable without a fresh poll. Polls run about every
# 1.5s, but a busy laptop (models on the same Python process) can stall one for several
# seconds; at 3s that paused task processing and the dashboard showed the camera as off.
# Writes stay safe meanwhile: the database rejects observations for an ended session or
# an old revision or activity (guard_managed_observation, migration 0520). It stays well
# under the one-camera writer lease (station_lease.TTL_SECONDS, 10s), so this camera stops
# writing before another camera can take the station over.
SESSION_LEASE_SECONDS = 7.0
# One tick a poll: lease, report, session and marks in a single request.
POLL_SECONDS = 1.5


@dataclass(frozen=True)
class SessionLease:
    session: Session | None
    checked_at: float
    activated_at: float


class StationSessionState:
    """Thread-safe immutable frame context. Expired/failed reads pause task checks."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self._lease: SessionLease | None = None

    def confirm(self, session: Session | None, checked_at: float | None = None) -> None:
        """`checked_at`: when the check began (before the writer claim), so the lease never
        outlasts the one-camera writer lease it was granted under. Defaults to now."""
        now = self.clock()
        checked = now if checked_at is None else min(checked_at, now)
        with self._lock:
            previous = self._lease
            changed = previous is None or previous.session != session
            self._lease = SessionLease(session, checked, now if changed else previous.activated_at)

    def invalidate(self) -> None:
        with self._lock:
            self._lease = None

    def for_frame(self, captured_at: float) -> Session | None:
        with self._lock:
            lease = self._lease
        if (
            lease is None
            or self.clock() - lease.checked_at > SESSION_LEASE_SECONDS
            or captured_at < lease.activated_at
            or lease.session is None
            or lease.session.ended_at is not None
            or lease.session.current_activity_id is None
        ):
            return None
        return lease.session


STATION_SESSION = StationSessionState()
# Set to run the next station tick now instead of waiting out the poll interval: the dashboard
# asks for it right after it changes the session, so vision follows a reset or a new activity
# within one request instead of up to POLL_SECONDS later.
WAKE = threading.Event()


def frame_activity(tasks, seat_id: str, ctx: dict) -> str | None:
    """Use one pinned session/task for the entire frame; legacy mode is unchanged."""
    if ctx.get("session_managed"):
        session = ctx.get("session")
        return session.current_activity_id if session else None
    return tasks.for_seat(seat_id)


class StationSessionSync:
    """Polls the station tick: one request that holds the one-camera lease, reports what this
    camera is doing, and returns the station's session and the teacher's review marks.

    `station` is a vision.station.ActiveStation (the dashboard's station) or a
    fixed station id. With no station yet, nothing is read or reported. A poll
    that started before a station change is discarded, never confirmed.
    """

    def __init__(
        self,
        client,
        station=None,
        state=STATION_SESSION,
        poll_seconds=POLL_SECONDS,
        lease=None,
        marks=None,
    ):
        from vision import station as station_module
        from vision.review_marks import MARKS

        if station is None:
            station = station_module.STATION
        elif isinstance(station, str):
            station = station_module.ActiveStation(station, pinned=True)
        self.client = client
        self.station = station
        self.station_id: str | None = station.get()
        self.state = state
        self.poll_seconds = poll_seconds
        self.marks = marks if marks is not None else MARKS
        # One camera per station (vision.station_lease). None = no guard (tests).
        self.lease = lease
        self._leased_station: str | None = None
        self._stop = threading.Event()
        self._wake = WAKE
        self._thread: threading.Thread | None = None

    def _tick(self, station_id: str) -> dict:
        writer = self.lease.writer_id if self.lease is not None else uuid.uuid4()
        ttl = self.lease.ttl if self.lease is not None else 10
        return (
            self.client.rpc(
                "station_tick",
                {
                    "p_station_id": station_id,
                    "p_writer_id": str(writer),
                    "p_ttl_seconds": ttl,
                    "p_supported_activity_ids": list(activities.load_activities()),
                },
            )
            .execute()
            .data
        )

    def _pause(self) -> None:
        self.state.invalidate()
        self.marks.clear()

    def check_once(self) -> Session | None:
        station_id, generation = self.station.snapshot()
        self.station_id = station_id
        if station_id is None:
            self._pause()  # no teacher station yet: tasks stay paused
            self._release_lease()
            return None
        started = self.state.clock()  # before the tick: the lease starts here
        try:
            if self._leased_station not in (None, station_id):
                self._release_lease()  # the station changed: hand the old one over
            self._leased_station = station_id
            tick = self._tick(station_id)
            if self.lease is not None and not self.lease.apply(station_id, tick):
                # Another camera holds this station: pause and try again on the next poll.
                self._pause()
                return None
            raw = tick.get("session")
            session = Session.model_validate(raw) if raw else None
            if session and session.station_id != station_id:
                raise ValueError("station mismatch")
            if session and not session.ended_at and session.current_activity_id:
                try:
                    activities.get(session.current_activity_id)
                except KeyError:
                    self._pause()  # the tick already reported unsupported_activity
                    return None
            if self._stop.is_set() or self.station.generation != generation:
                self._pause()  # stopped, or the station changed mid-poll
                return None
            self.state.confirm(session, checked_at=started)
            self._apply_marks(session, tick.get("marks") or [])
            return session
        except Exception:
            self._pause()
            log.warning("station session sync unavailable; task processing paused")
            raise

    def _apply_marks(self, session: Session | None, marks: list[dict]) -> None:
        if session is None or session.ended_at is not None:
            self.marks.clear()
            return
        from vision.review_marks import parse_time

        self.marks.replace(
            str(session.id), {m["seat_id"]: parse_time(m["marked_at"]) for m in marks}
        )

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="station-session-sync", daemon=True)
        self._thread.start()

    def _release_lease(self) -> None:
        if self.lease is not None and self._leased_station is not None:
            self.lease.release(self._leased_station)
        self._leased_station = None

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.state.invalidate()
        if self._thread:
            self._thread.join(timeout=2)
        self._release_lease()  # a camera that stops hands the station over at once

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                pass  # Already sanitized/logged; retry without blocking the camera.
            self._wake.wait(self.poll_seconds)
            self._wake.clear()


def sync_from_env() -> StationSessionSync | None:
    """The station tick for this laptop, or None when there is nothing to follow.

    Follows vision.station.STATION; one camera per station (the lease). Offline (no
    credentials) there is no database and tasks come from CUES_TASK.
    """
    from vision.station_lease import StationLease
    from vision.supabase_client import get_client

    STATION_SESSION.invalidate()
    client = get_client()
    if client is None:
        return None
    return StationSessionSync(client, lease=StationLease(client))
