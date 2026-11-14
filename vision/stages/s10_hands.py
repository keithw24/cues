"""Hand tracking: MediaPipe hand landmarks, assigned to a seat by wrist position.

Writes ctx["hands"] = {seat_id: [Hand, ...]}. Hands in the dead band near the
divider are dropped.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.grouping import GROUPING
from vision.perception import Hand
from vision.stages.s00_seats import seat_color

FLAG = "vision.hands"

# MediaPipe hand skeleton (pairs of landmark indices).
CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]  # fmt: skip


def hands_from_result(result, zones=GROUPING, ctx=None) -> dict[str, list[Hand]]:
    """Convert a MediaPipe HandLandmarkerResult into Hand lists per seat or person."""
    by_seat: dict[str, list[Hand]] = {}
    for landmarks, handedness in zip(result.hand_landmarks, result.handedness, strict=False):
        points = np.array([[p.x, p.y, p.z] for p in landmarks], dtype=np.float32)
        seat = zones.hand_owner(points, ctx)
        if seat is None:
            continue
        side = handedness[0].category_name if handedness else "Right"
        by_seat.setdefault(seat, []).append(Hand(points, side, seat))
    return by_seat


class HandsStage:
    name = "hands"
    rate_hz = None  # every frame

    def __init__(self, detector=None, zones=GROUPING) -> None:
        self.zones = zones
        self._detector = detector

    @property
    def detector(self):
        if self._detector is None:
            from vision import models

            self._detector = models.hand_landmarker(num_hands=4)
        return self._detector

    def process(self, frame, ctx) -> None:
        import mediapipe as mp

        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        result = self.detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        ctx["hands"] = hands_from_result(result, self.zones, ctx)

    def draw(self, image, ctx) -> None:
        from vision import overlay

        h, w = image.shape[:2]
        if self.zones.mode == "people" and not overlay.debug():
            for seat, hands in ctx.get("hands", {}).items():  # small dots only
                for hand in hands:
                    for x, y, _ in hand.landmarks[[0, 4, 8, 12, 16, 20]]:
                        cv2.circle(image, (int(x * w), int(y * h)), 3, seat_color(seat), -1)
            return
        for seat, hands in ctx.get("hands", {}).items():
            color = seat_color(seat)
            for hand in hands:
                pts = [(int(x * w), int(y * h)) for x, y, _ in hand.landmarks]
                for a, b in CONNECTIONS:
                    cv2.line(image, pts[a], pts[b], color, 2)
                for p in pts:
                    cv2.circle(image, p, 3, color, -1)


def create_stage() -> HandsStage:
    return HandsStage()
