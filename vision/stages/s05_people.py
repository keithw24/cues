"""Finds and tracks people (people mode only). Runs before hands and faces.

Writes:
    ctx["people"]     -> {person_id: Person} for people visible in this frame
    ctx["person_ids"] -> every live id, including people out of view for less
                         than RELEASE_SECONDS (so status can report tracking_lost)

This stage has no feature flag: every other stage depends on it.
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


def person_label(pid: str, ctx) -> list[str]:
    """Two short lines: 'P1  raise_hand 0.82' and 'done  attempt_success  neutral'."""
    short = pid.rsplit("-", 1)[-1]
    match = ctx.get("match", {}).get(pid)
    first = short
    if match is not None:
        score = "--" if match.score is None else f"{match.score:.2f}"
        first = f"{short}  {match.activity_id} {score}"
    second = [ctx.get("status", {}).get(pid, "")]
    if pid in ctx.get("last_event", {}):
        second.append(ctx["last_event"][pid])
    expression = ctx.get("expression", {}).get(pid)
    if expression:
        second.append(max(expression, key=expression.get))
    second_line = "  ".join(p for p in second if p)
    return [first, second_line] if second_line else [first]


class PeopleStage:
    name = "people"
    rate_hz = None

    def __init__(self, detector=None, grouping=GROUPING, tracker: PersonTracker | None = None):
        self.grouping = grouping
        self._detector = detector
        self.tracker = tracker or PersonTracker(getattr(grouping, "station_id", "S1"))
        self._last_ts = -1

    @property
    def active(self) -> bool:
        return True

    def load(self) -> None:
        """Load the model now (called by Pipeline.start before the first frame)."""
        _ = self.detector

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
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly increasing millisecond timestamps.
        ts = max(int(frame.timestamp * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self.detector.detect_for_video(image, ts)
        ctx["people"] = self.tracker.update(frame.timestamp, poses_from_result(result))
        ctx["person_ids"] = self.tracker.live_ids

    def draw(self, image, ctx) -> None:
        """Debug overlay only: the pose box and label. The normal overlay is s90_overlay."""
        from vision import overlay

        if not overlay.debug():
            return
        h, w = image.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        for pid, person in ctx.get("people", {}).items():
            x0, y0, x1, y1 = person.box
            p0, p1 = (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h))
            color = person_color(pid)
            cv2.rectangle(image, p0, p1, color, 2)
            lines = person_label(pid, ctx)
            top = max(0, p0[1] - 22 * len(lines) - 4)
            width = max(cv2.getTextSize(t, font, 0.5, 1)[0][0] for t in lines) + 10
            cv2.rectangle(image, (p0[0], top), (p0[0] + width, p0[1]), color, -1)
            for i, text in enumerate(lines):
                cv2.putText(
                    image,
                    text,
                    (p0[0] + 5, top + 17 + 22 * i),
                    font,
                    0.5,
                    (0, 0, 0),
                    1,
                    cv2.LINE_AA,
                )


def create_stage() -> PeopleStage:
    return PeopleStage()
