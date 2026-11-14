"""Face detection: one face box and face crop per seat.

Writes ctx["faces"] = {seat_id: Face}. If a seat has several faces, the
largest one is kept. The crop (RGB, with padding) feeds the expression stage.
No face recognition: faces are only located, never identified.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.grouping import GROUPING
from vision.people import person_color as seat_color
from vision.perception import Face

FLAG = "vision.faces"
PADDING = 0.10


def padded_box(x: int, y: int, bw: int, bh: int, w: int, h: int, pad: float = PADDING):
    px, py = int(bw * pad), int(bh * pad)
    return max(0, x - px), max(0, y - py), min(w, x + bw + px), min(h, y + bh + py)


def faces_from_result(result, rgb: np.ndarray, zones=GROUPING, ctx=None) -> dict[str, Face]:
    """Convert a MediaPipe FaceDetectorResult into one Face per seat."""
    h, w = rgb.shape[:2]
    best: dict[str, tuple[int, Face]] = {}
    for det in result.detections:
        b = det.bounding_box
        if b.width <= 0 or b.height <= 0:
            continue
        norm_box = (
            b.origin_x / w,
            b.origin_y / h,
            (b.origin_x + b.width) / w,
            (b.origin_y + b.height) / h,
        )
        cx, cy = (b.origin_x + b.width / 2) / w, (b.origin_y + b.height / 2) / h
        seat = zones.face_owner(cx, cy, norm_box, ctx)
        if seat is None:
            continue
        x0, y0, x1, y1 = padded_box(b.origin_x, b.origin_y, b.width, b.height, w, h)
        crop = rgb[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        area = b.width * b.height
        if seat not in best or area > best[seat][0]:
            best[seat] = (area, Face((x0, y0, x1, y1), crop.copy(), seat))
    return {seat: face for seat, (_, face) in best.items()}


class FacesStage:
    name = "faces"
    rate_hz = 5.0

    def __init__(self, detector=None, zones=GROUPING) -> None:
        self.zones = zones
        self._detector = detector

    def load(self) -> None:
        """Load the model now (called by Pipeline.start before the first frame)."""
        _ = self.detector

    @property
    def detector(self):
        if self._detector is None:
            from vision import models

            self._detector = models.face_detector()
        return self._detector

    def process(self, frame, ctx) -> None:
        import mediapipe as mp

        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        result = self.detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        ctx["faces"] = faces_from_result(result, rgb, self.zones, ctx)

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if not overlay.debug():
            return
        for seat, face in ctx.get("faces", {}).items():
            x0, y0, x1, y1 = face.box
            cv2.rectangle(image, (x0, y0), (x1, y1), seat_color(seat), 2)


def create_stage() -> FacesStage:
    return FacesStage()
