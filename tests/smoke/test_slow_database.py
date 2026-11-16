"""Smoke test: a slow database must never build a backlog or take good rows down with bad ones.

No database needed: a stand-in sink adds the latency a hosted Supabase has (100-300 ms per
request, against ~5 ms locally). This is the failure that locked the project out: the old
writer sent one row per request from an unbounded queue, so at 200 ms and 10 people it fell
further behind every second and the agent (which rejects rows older than 3 s) saw nothing.
"""

import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from shared.contracts import SeatState
from vision.events import Emitter

pytestmark = pytest.mark.smoke


class SlowSink:
    def __init__(self, latency: float, reject_seat: str | None = None):
        self.latency = latency
        self.reject_seat = reject_seat
        self.requests = 0
        self.written: list[tuple[str, float]] = []  # (seat, age of the row when written)
        self.lock = threading.Lock()

    def write_events(self, rows):
        time.sleep(self.latency)

    def write_seat_states(self, rows):
        time.sleep(self.latency)
        with self.lock:
            self.requests += 1
        if self.reject_seat and any(r["seat_id"] == self.reject_seat for r in rows):
            raise APIError({"message": "stale revision", "code": "40001"})
        now = datetime.now(UTC)
        with self.lock:
            for row in rows:
                sent = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                self.written.append((row["seat_id"], (now - sent).total_seconds()))


def publish(emitter: Emitter, people: int, seconds: float) -> None:
    """Every person's status once a second, like vision's heartbeat."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        started = time.monotonic()
        for p in range(people):
            emitter.update_seat_state(
                SeatState(
                    seat_id=f"S1-P{p + 1}",
                    session_id=emitter.session_id,
                    status="in_progress",
                    updated_at=datetime.now(UTC),
                )
            )
        time.sleep(max(0.0, 1.0 - (time.monotonic() - started)))


@pytest.mark.parametrize("latency", [0.005, 0.2, 0.3])
def test_rows_stay_fresh_at_any_latency(latency):
    sink = SlowSink(latency)
    emitter = Emitter(sink, session_id=uuid4(), station_id="S1")
    publish(emitter, people=10, seconds=6)
    emitter.flush()
    emitter.close()
    assert sink.written, "nothing was written"
    newest_age = sink.written[-1][1]
    # The agent drops anything older than 3 s; allow one flush interval plus the latency.
    assert newest_age < 2.0 + latency, f"newest row was {newest_age:.1f}s old"
    # One request per flush, not one per row: about two a second at most.
    assert sink.requests <= 6 * 3, f"{sink.requests} requests for 6 s"


def test_one_rejected_row_does_not_lose_the_others():
    sink = SlowSink(0.0, reject_seat="S1-P3")
    emitter = Emitter(sink, session_id=uuid4(), station_id="S1")
    for p in range(5):
        emitter.update_seat_state(
            SeatState(
                seat_id=f"S1-P{p + 1}",
                session_id=emitter.session_id,
                status="in_progress",
                updated_at=datetime.now(UTC),
            )
        )
    emitter.flush()
    emitter.close()
    written = {seat for seat, _ in sink.written}
    assert written == {"S1-P1", "S1-P2", "S1-P4", "S1-P5"}
