"""Seats mode only: draws the seat divider and dead band. Infrastructure: no flag.

Also holds seat_color(), which every stage uses to colour a seat or person.
"""

from __future__ import annotations

import cv2

from vision.grouping import GROUPING
from vision.people import person_color

DIVIDER_COLOR = (255, 255, 255)
BAND_COLOR = (90, 90, 90)
SEAT_COLORS = {"L": (255, 160, 0), "R": (0, 200, 255)}  # BGR: blue-ish left, amber right


def seat_color(seat_id: str) -> tuple[int, int, int]:
    if "-P" in seat_id:
        return person_color(seat_id)
    return SEAT_COLORS.get(seat_id[-1], (200, 200, 200))


class SeatsStage:
    name = "seats"
    rate_hz = None

    def __init__(self, zones=GROUPING) -> None:
        self.zones = zones

    def process(self, frame, ctx) -> None:
        if self.zones.mode == "seats":
            ctx["seats"] = self.zones.as_dict()

    def draw(self, image, ctx) -> None:
        if self.zones.mode != "seats":
            return  # people mode draws person boxes instead (s05_people)
        h, w = image.shape[:2]
        x = int(self.zones.divider * w)
        band = int(self.zones.dead_band * w)
        cv2.line(image, (x - band, 0), (x - band, h), BAND_COLOR, 1)
        cv2.line(image, (x + band, 0), (x + band, h), BAND_COLOR, 1)
        cv2.line(image, (x, 0), (x, h), DIVIDER_COLOR, 2)
        cv2.putText(
            image,
            self.zones.left_id,
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            seat_color(self.zones.left_id),
            2,
        )
        cv2.putText(
            image,
            self.zones.right_id,
            (w - 80, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            seat_color(self.zones.right_id),
            2,
        )


def create_stage() -> SeatsStage:
    return SeatsStage()
