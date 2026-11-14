"""Follow teacher-managed station sessions. Camera data never enters this module."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from shared.contracts import Session
from vision import activities

log = logging.getLogger(__name__)
SESSION_LEASE_SECONDS = 3.0


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

    def confirm(self, session: Session | None) -> None:
        now = self.clock()
        with self._lock:
            previous = self._lease
            changed = previous is None or previous.session != session
            self._lease = SessionLease(session, now, now if changed else previous.activated_at)

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


def frame_activity(tasks, seat_id: str, ctx: dict) -> str | None:
    """Use one pinned session/task for the entire frame; legacy mode is unchanged."""
    if ctx.get("session_managed"):
        session = ctx.get("session")
        return session.current_activity_id if session else None
    return tasks.for_seat(seat_id)


class StationSessionSync:
    def __init__(self, client, station_id: str, state=STATION_SESSION, poll_seconds=1.0):
        self.client = client
        self.station_id = station_id
        self.state = state
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _report(self, session: Session | None, status: str, error: str | None = None):
        self.client.rpc(
            "report_station_session",
            {
                "p_station_id": self.station_id,
                "p_session_id": str(session.id) if session else None,
                "p_revision": session.revision if session else None,
                "p_activity_id": session.current_activity_id
                if session and status != "idle"
                else None,
                "p_status": status,
                "p_error": error,
                "p_supported_activity_ids": list(activities.load_activities()),
            },
        ).execute()

    def check_once(self) -> Session | None:
        try:
            rows = (
                self.client.table("sessions")
                .select("id,station_id,current_activity_id,started_at,ended_at,revision")
                .eq("station_id", self.station_id)
                .is_("ended_at", "null")
                .limit(2)
                .execute()
                .data
            )
            if len(rows) > 1:
                raise ValueError("ambiguous active station session")
            if not rows:
                rows = (
                    self.client.table("sessions")
                    .select("id,station_id,current_activity_id,started_at,ended_at,revision")
                    .eq("station_id", self.station_id)
                    .order("started_at", desc=True)
                    .limit(1)
                    .execute()
                    .data
                )
            session = Session.model_validate(rows[0]) if rows else None
            if session and session.station_id != self.station_id:
                raise ValueError("station mismatch")
            if session and not session.ended_at and session.current_activity_id:
                try:
                    activities.get(session.current_activity_id)
                except KeyError:
                    self.state.invalidate()
                    self._report(session, "error", "unsupported_activity")
                    return None
                status = "ready"
            else:
                status = "idle"
            # A failed acknowledgement must not claim that the station is ready.
            self._report(session, status)
            if self._stop.is_set():
                self.state.invalidate()
                return None
            self.state.confirm(session)
            return session
        except Exception:
            self.state.invalidate()
            log.warning("station session sync unavailable; task processing paused")
            raise

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="station-session-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.state.invalidate()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                pass  # Already sanitized/logged; retry without blocking the camera.
            self._stop.wait(self.poll_seconds)
