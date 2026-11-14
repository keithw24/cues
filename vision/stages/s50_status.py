"""Task status and events: the vision service's output to the rest of Cues.

On each frame this stage:
1. Reads each seat's match score, and whether a hand and a face are visible,
   from ctx (written by the earlier stages).
2. Feeds them to that seat's SeatTracker (vision/status.py), which returns
   status changes and events. A new tracker starts whenever the seat's task
   changes.
3. Feeds the smoothed expression distribution to that seat's ExpressionTracker.
4. Turns the results into shared contract objects (shared.contracts.Event and
   SeatState) and sends them through the emitter: local JSONL by default,
   Supabase when `vision.supabase_events` is on and keys are set.
5. Keeps the last few events in ctx["events"] so vision.watch can print them.

Seat state is sent when the status changes and otherwise once per second, so
the dashboard sees live scores without a write on every frame.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

from vision import activities
from vision.activities import TASKS
from vision.seats import ZONES
from vision.status import ExpressionTracker, SeatTracker, StatusEvent

FLAG = "vision.task_status"
SEAT_STATE_INTERVAL = 1.0
RECENT_EVENTS = 20

log = logging.getLogger(__name__)


def format_event(seat_id: str, activity_id: str, event: StatusEvent) -> str:
    """One-line summary, e.g. `EVENT attempt_miss S1-L thumbs_up score=0.31`."""
    parts = [f"EVENT {event.type}", seat_id, activity_id]
    if event.score is not None:
        parts.append(f"score={event.score:.2f}")
    if event.payload:
        parts.append(" ".join(f"{k}={v}" for k, v in event.payload.items()))
    return " ".join(parts)


class StatusStage:
    name = "status"
    rate_hz = None

    def __init__(self, emitter=None, tasks=TASKS, zones=ZONES) -> None:
        self.tasks = tasks
        self.zones = zones
        self._emitter = emitter
        self._trackers: dict[str, SeatTracker] = {}
        self._expression: dict[str, ExpressionTracker] = {}
        self._last_state: dict[str, tuple[str, float]] = {}  # seat -> (status, time sent)
        self.recent: deque[str] = deque(maxlen=RECENT_EVENTS)

    @property
    def emitter(self):
        if self._emitter is None:
            from vision.events import emitter_from_env

            self._emitter = emitter_from_env()
        return self._emitter

    def process(self, frame, ctx) -> None:
        t = frame.timestamp
        matches = ctx.get("match", {})
        hands = ctx.get("hands", {})
        faces = ctx.get("faces", {})
        expressions = ctx.get("expression", {})
        for seat in self.zones.seat_ids:
            activity = activities.get(self.tasks.for_seat(seat))
            tracker = self._trackers.get(seat)
            if tracker is None or tracker.activity.id != activity.id:
                tracker = self._trackers[seat] = SeatTracker(seat, activity)
            match = matches.get(seat)
            score = match.score if match is not None and match.activity_id == activity.id else None
            events = tracker.update(t, score, seat in hands, seat in faces)
            expr_tracker = self._expression.setdefault(seat, ExpressionTracker())
            events += expr_tracker.update(t, expressions.get(seat))
            for event in events:
                self._send_event(seat, activity.id, event)
            self._maybe_send_state(seat, tracker, score, expressions.get(seat), t)
        ctx["status"] = {seat: tr.status for seat, tr in self._trackers.items()}
        ctx["events"] = list(self.recent)

    def _send_event(self, seat: str, activity_id: str, event: StatusEvent) -> None:
        from shared.contracts import Event

        line = format_event(seat, activity_id, event)
        self.recent.append(line)
        log.info(line)
        self.emitter.emit(
            Event(
                session_id=self.emitter.session_id,
                station_id=self.emitter.station_id,
                seat_id=seat,
                type=event.type,
                activity_id=activity_id,
                score=event.score,
                payload=event.payload or {"source": "auto"},
                created_at=datetime.now(UTC),
            )
        )

    def _maybe_send_state(self, seat, tracker: SeatTracker, score, distribution, t) -> None:
        from shared.contracts import ExpressionContext, SeatState

        last = self._last_state.get(seat)
        if last is not None and last[0] == tracker.status and t - last[1] < SEAT_STATE_INTERVAL:
            return
        self._last_state[seat] = (tracker.status, t)
        expression = None
        if distribution:
            label = max(distribution, key=distribution.get)
            expression = ExpressionContext(label=label, probability=distribution[label])
        self.emitter.update_seat_state(
            SeatState(
                seat_id=seat,
                session_id=self.emitter.session_id,
                status=tracker.status,
                updated_at=datetime.now(UTC),
                activity_id=tracker.activity.id,
                tracking_valid=tracker.status != "tracking_lost",
                task_score=score,
                expression_context=expression,
            )
        )

    def draw(self, image, ctx) -> None:
        import cv2

        h, w = image.shape[:2]
        for seat, status in ctx.get("status", {}).items():
            x = 10 if seat == self.zones.left_id else w // 2 + 10
            cv2.putText(image, status, (x, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    def close(self) -> None:
        if self._emitter is not None:
            self._emitter.close()


def create_stage() -> StatusStage:
    return StatusStage()
