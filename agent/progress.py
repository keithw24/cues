"""Deterministic progress evaluation; no service calls or alert writes."""

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Literal

from shared.contracts import Activity, SeatState


@dataclass(frozen=True)
class ProgressDecision:
    action: Literal["wait", "evaluate_agent", "completed"]
    trend: Literal["improving", "not_improving", "unknown"]
    stalled_seconds: float
    supporting_expression: bool


class ProgressEvaluator:
    def __init__(
        self,
        activity: Activity,
        window_seconds: float = 6,
        min_increase: float = 0.10,
        max_gap_seconds: float = 2,
    ):
        if window_seconds <= 0 or max_gap_seconds <= 0 or min_increase <= 0:
            raise ValueError("configuration must be positive")
        self.activity = activity
        self.window = window_seconds
        self.increase = min_increase
        self.max_gap = max_gap_seconds
        self.reset()

    def reset(self):
        self.key = None
        self.last = None
        self.started = None
        self.samples = []
        self.fired = False
        self.completed = False

    def update(self, snapshot: SeatState, *, now: datetime) -> ProgressDecision:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        wait = ProgressDecision("wait", "unknown", 0, False)
        key = (snapshot.session_id, snapshot.seat_id, snapshot.activity_id)
        if key != self.key:
            self.reset()
            self.key = key
        if snapshot.activity_id != self.activity.id:
            return wait
        if self.last is not None and snapshot.updated_at <= self.last:
            return wait
        if snapshot.updated_at > now:
            return wait
        if snapshot.status == "done" or self.completed:
            self.completed = True
            self.samples = []
            self.started = None
            self.last = snapshot.updated_at
            return ProgressDecision("completed", "unknown", 0, False)
        gap = (
            self.last is not None
            and (snapshot.updated_at - self.last).total_seconds() > self.max_gap
        )
        if (
            gap
            or (now - snapshot.updated_at).total_seconds() > self.max_gap
            or snapshot.tracking_valid is not True
            or snapshot.status in ("idle", "tracking_lost")
        ):
            self.samples = []
            self.started = None
            self.fired = False
            self.last = snapshot.updated_at
            return wait
        if self.last is not None and (snapshot.updated_at - self.last).total_seconds() < 1:
            return wait
        self.last = snapshot.updated_at
        if self.started is None:
            self.started = self.last
        self.samples.append((self.last, snapshot.task_score))
        self.samples = [
            (t, s) for t, s in self.samples if (self.last - t).total_seconds() <= self.window
        ]
        trend = "unknown"
        if self.activity.check_type == "gesture":
            if snapshot.task_score is None:
                self.started = None
                self.samples = []
                return wait
            if (self.last - self.samples[0][0]).total_seconds() < self.window:
                return wait
            early = [
                s
                for t, s in self.samples
                if s is not None and (self.last - t).total_seconds() > self.window / 2
            ]
            late = [
                s
                for t, s in self.samples
                if s is not None and (self.last - t).total_seconds() <= self.window / 2
            ]
            if not early or not late:
                return wait
            trend = "improving" if mean(late) - mean(early) >= self.increase else "not_improving"
            if trend == "improving":
                self.started = self.last
                self.fired = False
        stalled = (self.last - self.started).total_seconds()
        eligible = trend != "improving" and stalled >= self.activity.no_progress_seconds
        context = snapshot.expression_context
        supporting = bool(
            eligible
            and context
            and context.label in ("anger", "fear", "sadness")
            and context.probability >= 0.5
            and (context.duration_seconds or 0) >= 5
        )
        action = "wait"
        if eligible and not self.fired:
            action = "evaluate_agent"
            self.fired = True
        return ProgressDecision(action, trend, stalled, supporting)
