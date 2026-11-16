"""Event emitter.

The vision service reports what happens at each seat as structured events
(PRD §17.1) and keeps the live `seat_state` row for each seat up to date.

* `emit(event)` and `update_seat_state(state)` validate shared contracts and queue
  writes. A background thread sends them in batches (latest seat state wins), so a slow
  connection never stalls the camera or builds a backlog.
* With `vision.supabase_events` enabled and SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
  set (root .env), events go
  to the Supabase `events` table and seat state to `seat_state`.
* Without them, or if a Supabase write fails, the same rows are appended to
  vision/logs/events.jsonl (appended) and vision/logs/seat_state.json (latest row
  per seat).

Try it from the repo root:

    uv run python -m vision.events --demo
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from shared.contracts import Event, SeatState

log = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent / "logs"


class Sink(Protocol):
    """Where rows go. Both methods take a whole batch and raise if it cannot be written."""

    def write_events(self, rows: list[dict[str, Any]]) -> None: ...
    def write_seat_states(self, rows: list[dict[str, Any]]) -> None: ...


class JsonlSink:
    """Local files, used offline and as the fallback. They stay on this laptop.

    * Events are appended to events.jsonl (an audit log, like the events table).
    * Seat state keeps only the LATEST row per seat_id in seat_state.json, like
      the Supabase upsert. Appending would build a per-second history of each
      child's live expression, which the product rules forbid.
    """

    def __init__(self, directory: Path = LOG_DIR) -> None:
        self.directory = directory
        self._latest: dict[str, dict[str, Any]] = {}

    def write_events(self, rows: list[dict[str, Any]]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.directory / "events.jsonl", "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def write_seat_states(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._latest[str(row["seat_id"])] = row
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "seat_state.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._latest, indent=1))
        tmp.replace(path)


class SupabaseSink:
    """One request per batch: a single insert for events, a single upsert for seat state."""

    def __init__(self, client) -> None:
        self.client = client

    def write_events(self, rows: list[dict[str, Any]]) -> None:
        self.client.table("events").insert(rows).execute()

    def write_seat_states(self, rows: list[dict[str, Any]]) -> None:
        payload = []
        for row in rows:
            row = dict(row)
            # Legacy mode must still work before lifecycle migration 005 exists.
            if row.get("session_revision") is None:
                row.pop("session_revision", None)
            payload.append(row)
        # One request has one set of columns: group rows that carry the same keys.
        by_keys: dict[tuple, list[dict[str, Any]]] = {}
        for row in payload:
            by_keys.setdefault(tuple(sorted(row)), []).append(row)
        for group in by_keys.values():
            self.client.table("seat_state").upsert(group, on_conflict="seat_id").execute()


FLUSH_INTERVAL = 1.0  # seconds between batches: one request a second per kind, like the heartbeat
MAX_EVENTS_QUEUED = 500  # beyond this the oldest events are dropped, never the camera's time


def _rejected_by_database(exc: Exception) -> bool:
    """The database answered and refused the request (as opposed to not answering)."""
    from postgrest.exceptions import APIError

    return isinstance(exc, APIError)


class Emitter:
    """Collects shared events/snapshots and writes them in batches on a background thread.

    Interface: emit(event), update_seat_state(state), flush(), close(), plus the producer
    defaults `session_id` and `station_id` (not injected into models).

    Why it is shaped this way. A request costs ~5 ms on a local database and 100-300 ms on a
    hosted one. Writing one row per request from an unbounded queue gives a capacity of
    1/latency rows per second; past that the queue (and the age of every row) grows forever.
    So:

    * seat state is latest-wins per seat: a newer snapshot replaces an unsent older one, so
      the backlog is at most one row per person however slow the database is;
    * everything pending goes out in one request per kind each flush;
    * events are kept in a bounded queue (oldest dropped first, counted and logged);
    * a batch the database rejects is split until the bad row is found, so one stale row
      never takes the good ones down with it. A row that cannot be written goes to the
      fallback sink (local files) when there is one.
    """

    def __init__(
        self,
        sink: Sink,
        fallback: Sink | None = None,
        session_id: uuid.UUID | str | None = None,
        station_id: str = "S1",
        flush_interval: float = FLUSH_INTERVAL,
    ) -> None:
        self.sink = sink
        self.fallback = fallback
        self.session_id = uuid.UUID(str(session_id)) if session_id is not None else uuid.uuid4()
        self.station_id = station_id
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._seat_states: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque()
        self._dropped_events = 0
        self._busy = False
        self._closed = False
        self._thread = threading.Thread(target=self._loop, name="emitter", daemon=True)
        self._thread.start()

    def emit(self, event: Event) -> None:
        """Queue a complete shared event without mutating the producer's model."""
        row = Event.model_validate(event.model_dump()).model_dump(mode="json")
        with self._lock:
            if len(self._events) >= MAX_EVENTS_QUEUED:
                self._events.popleft()
                self._dropped_events += 1
            self._events.append(row)

    def update_seat_state(self, state: SeatState) -> None:
        """Queue a complete snapshot; it replaces an unsent older one for the same seat."""
        row = SeatState.model_validate(state.model_dump()).model_dump(mode="json")
        with self._lock:
            self._seat_states[str(row["seat_id"])] = row

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until everything queued so far has been written (for tests and shutdown)."""
        deadline = time.monotonic() + timeout
        with self._wake:
            self._wake.notify_all()
            while (self._seat_states or self._events or self._busy) and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._wake.notify_all()
                self._wake.wait(min(remaining, 0.05))

    def close(self) -> None:
        self.flush()
        with self._wake:
            self._closed = True
            self._wake.notify_all()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while True:
            with self._wake:
                if not self._closed:
                    self._wake.wait(self._flush_interval)
                if self._closed and not (self._seat_states or self._events):
                    return
                seat_states = list(self._seat_states.values())
                events = list(self._events)
                self._seat_states.clear()
                self._events.clear()
                dropped, self._dropped_events = self._dropped_events, 0
                self._busy = bool(seat_states or events)
            if dropped:
                log.warning("dropped %d events: the database could not keep up", dropped)
            try:
                if seat_states:
                    self._write("seat_state", seat_states)
                if events:
                    self._write("event", events)
            finally:
                with self._wake:
                    self._busy = False
                    self._wake.notify_all()

    def _write(self, kind: str, rows: list[dict[str, Any]]) -> None:
        method = "write_events" if kind == "event" else "write_seat_states"
        try:
            getattr(self.sink, method)(rows)
            return
        except Exception as exc:
            if len(rows) > 1 and _rejected_by_database(exc):
                # One bad row (for example a stale revision) must not sink the rest. A timeout
                # or lost connection is not that: splitting would only repeat the wait.
                middle = len(rows) // 2
                self._write(kind, rows[:middle])
                self._write(kind, rows[middle:])
                return
            log.warning("%s write failed (%s); using fallback", kind, exc)
        if self.fallback is not None:
            try:
                getattr(self.fallback, method)(rows)
            except Exception:
                log.exception("fallback write failed")


def _current_station() -> str:
    """The service creates its emitter only once a station is set. The one-off
    `python -m vision.events --demo` check falls back to S1 (or CUES_STATION_ID)."""
    from vision.station import LEGACY_STATION, STATION

    return STATION.get() or LEGACY_STATION


def emitter_from_env() -> Emitter:
    """Supabase when the `vision.supabase_events` flag is on and keys are set;
    otherwise local JSONL. JSONL is always the fallback.

    The station is vision.station.STATION (the dashboard's station, or the CUES_STATION_ID
    dev override). Under Supabase every row carries the session the station tick pinned for
    its frame, so the emitter's own session id is only a placeholder; offline (JSONL only)
    it labels the run.
    """
    from vision import flags
    from vision.supabase_client import get_client

    local = JsonlSink()
    client = get_client() if flags.enabled("vision.supabase_events") else None
    if client is not None and not flags.enabled("vision.session_lifecycle"):
        raise RuntimeError(
            "vision.supabase_events needs vision.session_lifecycle: the session comes from "
            "the station tick. Turn both on, or turn supabase_events off."
        )
    sink: Sink = SupabaseSink(client) if client is not None else local
    emitter = Emitter(
        sink,
        fallback=local if client is not None else None,
        session_id=str(uuid.uuid4()),
        # StatusStage sets the dashboard's station before anything is written.
        station_id=_current_station(),
    )
    where = "Supabase" if client is not None else f"{LOG_DIR} (local only)"
    log.info("events go to %s, session %s", where, emitter.session_id)
    return emitter


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Send a demo event to check the setup.")
    parser.add_argument("--demo", action="store_true", help="send one fake attempt_success")
    args = parser.parse_args(argv)
    if not args.demo:
        parser.print_help()
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    emitter = emitter_from_env()
    try:
        emitter.emit(
            Event(
                session_id=emitter.session_id,
                station_id=emitter.station_id,
                type="attempt_success",
                seat_id=f"{emitter.station_id}-L",
                activity_id="raise_hand",
                score=1.0,
                payload={"source": "auto"},
                created_at=datetime.now(UTC),
            )
        )
        emitter.update_seat_state(
            SeatState(
                session_id=emitter.session_id,
                seat_id=f"{emitter.station_id}-L",
                status="done",
                activity_id="raise_hand",
                task_score=1.0,
                updated_at=datetime.now(UTC),
            )
        )
    finally:
        emitter.close()
    print(f"Sent a demo attempt_success for {emitter.station_id}-L.")


if __name__ == "__main__":
    main()
