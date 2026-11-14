"""Event emitter.

The vision service reports what happens at each seat as structured events
(PRD §17.1) and keeps the live `seat_state` row for each seat up to date.

* `emit(event)` and `update_seat_state(...)` return immediately. A background
  thread does the network work, so a slow connection never stalls the camera.
* With SUPABASE_URL and SUPABASE_KEY set, events go to the Supabase `events`
  table and seat state to `seat_state`.
* Without them, or if a Supabase write fails, the same rows are appended to
  vision/logs/events.jsonl and vision/logs/seat_state.jsonl.

Try it from the repo root:

    uv run --project vision python -m vision.events --demo
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent / "logs"

EVENT_TYPES = frozenset(
    {
        "attempt_success",
        "attempt_miss",
        "review_needed",
        "no_progress",
        "tracking_lost",
        "expression_context",
        "teacher_verified",
        "agent_invoked",
        "alert_created",
        "teacher_approved",
        "teacher_dismissed",
        "intervention_applied",
    }
)

SEAT_STATUSES = frozenset({"idle", "in_progress", "review", "done", "needs_help", "tracking_lost"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Event:
    """One row of the `events` table (PRD §17.1)."""

    type: str
    seat_id: str
    activity_id: str | None = None
    score: float | None = None
    payload: dict[str, Any] = field(default_factory=lambda: {"source": "auto"})
    session_id: str | None = None
    station_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {self.type!r}")
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be between 0 and 1, got {self.score}")

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


class Sink(Protocol):
    def write_event(self, row: dict[str, Any]) -> None: ...
    def write_seat_state(self, row: dict[str, Any]) -> None: ...


class JsonlSink:
    """Appends rows to local JSON-lines files. Used offline and as the fallback."""

    def __init__(self, directory: Path = LOG_DIR) -> None:
        self.directory = directory

    def _append(self, name: str, row: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.directory / name, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def write_event(self, row: dict[str, Any]) -> None:
        self._append("events.jsonl", row)

    def write_seat_state(self, row: dict[str, Any]) -> None:
        self._append("seat_state.jsonl", row)


class SupabaseSink:
    def __init__(self, client) -> None:
        self.client = client

    def write_event(self, row: dict[str, Any]) -> None:
        self.client.table("events").insert(row).execute()

    def write_seat_state(self, row: dict[str, Any]) -> None:
        self.client.table("seat_state").upsert(row, on_conflict="seat_id").execute()


class Emitter:
    """Queues events and seat-state updates and writes them on a background thread."""

    def __init__(
        self,
        sink: Sink,
        fallback: Sink | None = None,
        session_id: str | None = None,
        station_id: str = "S1",
    ) -> None:
        self.sink = sink
        self.fallback = fallback
        self.session_id = session_id
        self.station_id = station_id
        self._queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="emitter", daemon=True)
        self._thread.start()

    def emit(self, event: Event) -> None:
        event.session_id = event.session_id or self.session_id
        event.station_id = event.station_id or self.station_id
        self._queue.put(("event", event.to_row()))

    def update_seat_state(
        self,
        seat_id: str,
        *,
        status: str | None = None,
        activity_id: str | None = None,
        task_score: float | None = None,
        expression_context: dict[str, Any] | None = None,
    ) -> None:
        """Upsert the live seat_state row. Only fields that are passed are sent."""
        if status is not None and status not in SEAT_STATUSES:
            raise ValueError(f"unknown seat status {status!r}")
        row: dict[str, Any] = {"seat_id": seat_id, "updated_at": utc_now()}
        if self.session_id:
            row["session_id"] = self.session_id
        for key, value in (
            ("status", status),
            ("activity_id", activity_id),
            ("task_score", task_score),
            ("expression_context", expression_context),
        ):
            if value is not None:
                row[key] = value
        self._queue.put(("seat_state", row))

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until everything queued so far has been written (for tests and shutdown)."""
        done = threading.Event()
        self._queue.put(("flush", {"done": done}))
        done.wait(timeout)

    def close(self) -> None:
        self.flush()
        self._queue.put(None)
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            kind, row = item
            if kind == "flush":
                row["done"].set()
                continue
            self._write(kind, row)

    def _write(self, kind: str, row: dict[str, Any]) -> None:
        method = "write_event" if kind == "event" else "write_seat_state"
        try:
            getattr(self.sink, method)(row)
        except Exception as exc:
            log.warning("%s write failed (%s); using fallback", kind, exc)
            if self.fallback is not None:
                try:
                    getattr(self.fallback, method)(row)
                except Exception:
                    log.exception("fallback write failed")


def emitter_from_env() -> Emitter:
    """Supabase when configured, else local JSONL. JSONL is always the fallback.

    CUES_STATION_ID (default S1) and CUES_SESSION_ID (default: new UUID) set the ids.
    """
    from vision.supabase_client import get_client

    local = JsonlSink()
    client = get_client()
    sink: Sink = SupabaseSink(client) if client is not None else local
    log.info("events go to %s", "Supabase" if client is not None else f"{LOG_DIR}/*.jsonl")
    return Emitter(
        sink,
        fallback=local if client is not None else None,
        session_id=os.environ.get("CUES_SESSION_ID") or str(uuid.uuid4()),
        station_id=os.environ.get("CUES_STATION_ID", "S1"),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Send a demo event to check the setup.")
    parser.add_argument("--demo", action="store_true", help="send one fake attempt_success")
    args = parser.parse_args(argv)
    if not args.demo:
        parser.print_help()
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    emitter = emitter_from_env()
    emitter.emit(Event(type="attempt_success", seat_id="S1-L", activity_id="raise_hand", score=1.0))
    emitter.update_seat_state("S1-L", status="done", activity_id="raise_hand", task_score=1.0)
    emitter.close()
    print("Sent a demo attempt_success for S1-L.")


if __name__ == "__main__":
    main()
