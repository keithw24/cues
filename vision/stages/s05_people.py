"""Finds and tracks people (people mode only). Runs before hands and faces.

Writes:
    ctx["people"]     -> {person_id: Person} for people visible in this frame
    ctx["person_ids"] -> every live id, including people out of view for less
                         than RELEASE_SECONDS (so status can report tracking_lost)

In seats mode (CUES_GROUPING=seats) this stage does nothing. It has no feature
flag: switching CUES_GROUPING is how people mode is turned off.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.grouping import GROUPING
from vision.people import MAX_PEOPLE, PersonTracker, person_color


def poses_from_result(result) -> list[np.ndarray]:
    """MediaPipe PoseLandmarkerResult -> list of (33, 4) arrays: x, y, z, visibility."""
    poses = []
    for landmarks in result.pose_landmarks:
        poses.append(
            np.array(
                [
                    [p.x, p.y, p.z, p.visibility if p.visibility is not None else 1.0]
                    for p in landmarks
                ],
                dtype=np.float32,
            )
        )
    return poses


class PeopleStage:
    name = "people"
    rate_hz = None

    def __init__(self, detector=None, grouping=GROUPING, tracker: PersonTracker | None = None):
        self.grouping = grouping
        self._detector = detector
        self.tracker = tracker or PersonTracker(getattr(grouping, "station_id", "S1"))

    @property
    def active(self) -> bool:
        return getattr(self.grouping, "mode", "") == "people"

    @property
    def detector(self):
        if self._detector is None:
            from vision import models

            self._detector = models.pose_landmarker(num_poses=MAX_PEOPLE)
        return self._detector

    def process(self, frame, ctx) -> None:
        if not self.active:
            return
        import mediapipe as mp

        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        result = self.detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        ctx["people"] = self.tracker.update(frame.timestamp, poses_from_result(result))
        ctx["person_ids"] = self.tracker.live_ids

    def draw(self, image, ctx) -> None:
        if not self.active:
            return
        h, w = image.shape[:2]
        for pid, person in ctx.get("people", {}).items():
            x0, y0, x1, y1 = person.box
            p0, p1 = (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h))
            color = person_color(pid)
            cv2.rectangle(image, p0, p1, color, 2)
            label = pid.rsplit("-", 1)[-1]  # "P1"
            cv2.putText(
                image,
                label,
                (p0[0] + 4, max(16, p0[1] - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )


def create_stage() -> PeopleStage:
    return PeopleStage()
