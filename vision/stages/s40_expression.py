"""Facial-expression context: HSEmotion on each seat's face crop.

Keeps HSEmotion's native 8-class distribution (no classes dropped, no
renormalising) and averages it over a short rolling window, because single
frames are noisy. Writes ctx["expression"] = {seat_id: {label: probability}}.

This is model output used as supporting context only. It is not an emotional
state, never a diagnosis, and never on its own a sign that a student is
struggling.
"""

from __future__ import annotations

import time
from collections import deque

import cv2
import numpy as np

from vision.grouping import GROUPING
from vision.people import person_color as seat_color

# HSEmotion enet_b0_8 class order (idx_to_class), lower-cased.
LABELS = ("anger", "contempt", "disgust", "fear", "happiness", "neutral", "sadness", "surprise")
WINDOW_SECONDS = 2.0


class RollingAverage:
    """Average of probability vectors seen in the last `window` seconds."""

    def __init__(self, window: float = WINDOW_SECONDS) -> None:
        self.window = window
        self._items: deque[tuple[float, np.ndarray]] = deque()

    def add(self, probs: np.ndarray, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._items.append((now, np.asarray(probs, dtype=np.float64)))
        self._trim(now)

    def mean(self, now: float | None = None) -> np.ndarray | None:
        now = time.monotonic() if now is None else now
        self._trim(now)
        if not self._items:
            return None
        return np.mean([p for _, p in self._items], axis=0)

    def _trim(self, now: float) -> None:
        while self._items and now - self._items[0][0] > self.window:
            self._items.popleft()


def as_distribution(probs: np.ndarray) -> dict[str, float]:
    return {label: round(float(p), 3) for label, p in zip(LABELS, probs, strict=True)}


class ExpressionStage:
    name = "expression"
    rate_hz = 3.0

    def __init__(self, recognizer=None, zones=GROUPING, window: float = WINDOW_SECONDS) -> None:
        self.zones = zones
        self.window = window
        self._recognizer = recognizer
        self._averages: dict[str, RollingAverage] = {}

    def load(self) -> None:
        """Load the model now (called by Pipeline.start before the first frame)."""
        _ = self.recognizer

    @property
    def recognizer(self):
        if self._recognizer is None:
            from vision import models

            self._recognizer = models.expression_recognizer()
        return self._recognizer

    def process(self, frame, ctx) -> None:
        now = time.monotonic()
        for seat, face in ctx.get("faces", {}).items():
            _, scores = self.recognizer.predict_emotions(face.crop, logits=False)
            self._averages.setdefault(seat, RollingAverage(self.window)).add(scores, now)
        result = {}
        for seat, avg in self._averages.items():
            mean = avg.mean(now)
            if mean is not None:
                result[seat] = as_distribution(mean)
        ctx["expression"] = result

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if not overlay.debug():
            return
        for seat, dist in ctx.get("expression", {}).items():
            face = ctx.get("faces", {}).get(seat)
            if face is None:
                continue
            label = max(dist, key=dist.get)
            x0, y0 = face.box[0], max(14, face.box[1] - 6)
            cv2.putText(
                image,
                f"{label} {dist[label]:.2f}",
                (x0, y0),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                seat_color(seat),
                1,
            )


def create_stage() -> ExpressionStage:
    return ExpressionStage()
