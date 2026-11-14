"""The normal video overlay: one face box and one hand per person.

For each tracked person this stage draws, in that person's colour:

1. A box around their face, labelled with their id and the strongest
   expression probability, e.g. "P1  neutral 0.61". The face box is smoothed
   between face detections and kept for FACE_GRACE_SECONDS after a missed
   detection, so it does not jump or flicker.
2. Their one hand (the hand the gesture or raise-hand score is for, or their
   highest hand): the full MediaPipe skeleton (21 points and the lines between
   them) and a box around it, labelled with the task and score, e.g.
   "thumbs_up 0.82". The label colour shows where the score stands against the
   task's thresholds: green = success, orange = review band, grey = below.
3. A thin line from the hand's wrist to the bottom of the face box, so it is
   clear whose hand it is.

If a person's face is not visible, only the hand box is drawn and its label
starts with the person's id ("P1  thumbs_up 0.82").

The expression label is model output, shown as a probability. It is not an
emotional state. Detailed per-stage drawings are available with
CUES_OVERLAY=debug (vision.watch --debug).
"""

from __future__ import annotations

import cv2
import numpy as np

from vision import activities
from vision.grouping import GROUPING
from vision.people import person_color
from vision.stages.s10_hands import CONNECTIONS

FACE_SMOOTHING = 0.5  # weight of the newest face box
FACE_GRACE_SECONDS = 0.5
HAND_PADDING = 0.15
FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN, ORANGE, GREY, BLACK = (0, 190, 0), (0, 160, 255), (150, 150, 150), (0, 0, 0)


def short_id(pid: str) -> str:
    return pid.rsplit("-", 1)[-1]  # "S1-P1" -> "P1"


def score_color(activity_id: str, score: float | None) -> tuple[int, int, int]:
    if score is None:
        return GREY
    activity = activities.get(activity_id)
    if score >= activity.success_threshold:
        return GREEN
    if score >= activity.review_threshold:
        return ORANGE
    return GREY


def hand_box(landmarks: np.ndarray, w: int, h: int, pad: float = HAND_PADDING):
    xs, ys = landmarks[:, 0] * w, landmarks[:, 1] * h
    px, py = (xs.max() - xs.min()) * pad, (ys.max() - ys.min()) * pad
    return (int(xs.min() - px), int(ys.min() - py), int(xs.max() + px), int(ys.max() + py))


def label(image, text: str, x: int, y: int, fill) -> None:
    """Text on a filled tab whose bottom edge sits at y."""
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.5, 1)
    top = max(0, y - th - 8)
    cv2.rectangle(image, (x, top), (x + tw + 8, top + th + 8), fill, -1)
    cv2.putText(image, text, (x + 4, top + th + 3), FONT, 0.5, BLACK, 1, cv2.LINE_AA)


class OverlayStage:
    name = "overlay"
    rate_hz = None

    def __init__(self, grouping=GROUPING) -> None:
        self.grouping = grouping
        self._faces: dict[str, tuple[tuple[float, float, float, float], float]] = {}

    def process(self, frame, ctx) -> None:
        """Smooth face boxes and drop ones not seen for FACE_GRACE_SECONDS."""
        t = frame.timestamp
        for pid, face in ctx.get("faces", {}).items():
            box = tuple(float(v) for v in face.box)
            old = self._faces.get(pid)
            if old is not None:
                box = tuple(
                    FACE_SMOOTHING * n + (1 - FACE_SMOOTHING) * o
                    for n, o in zip(box, old[0], strict=True)
                )
            self._faces[pid] = (box, t)
        for pid in [p for p, (_, seen) in self._faces.items() if t - seen > FACE_GRACE_SECONDS]:
            del self._faces[pid]
        ctx["overlay_faces"] = {pid: box for pid, (box, _) in self._faces.items()}

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if overlay.debug():
            return  # debug mode draws each stage's own detail instead
        h, w = image.shape[:2]
        faces = ctx.get("overlay_faces", {})
        labels = []  # drawn last, so hands never cover a label
        for pid in self.grouping.ids(ctx):
            color = person_color(pid)
            face = faces.get(pid)
            match = ctx.get("match", {}).get(pid)
            hand = match.hand if match is not None and match.hand is not None else None
            if hand is None:  # no score yet: still show the person's highest hand
                person_hands = ctx.get("hands", {}).get(pid, [])
                hand = min(person_hands, key=lambda hd: hd.wrist[1]) if person_hands else None

            if face is not None:
                x0, y0, x1, y1 = (int(v) for v in face)
                cv2.rectangle(image, (x0, y0), (x1, y1), color, 2)
                text = short_id(pid)
                dist = ctx.get("expression", {}).get(pid)
                if dist:
                    top = max(dist, key=dist.get)
                    text += f"  {top} {dist[top]:.2f}"
                labels.append((text, x0, y0, color))

            if hand is not None:
                pts = [(int(x * w), int(y * h)) for x, y, _ in hand.landmarks]
                if face is not None:
                    fx = (int(face[0]) + int(face[2])) // 2
                    cv2.line(image, pts[0], (fx, int(face[3])), color, 1, cv2.LINE_AA)
                for a, b in CONNECTIONS:
                    cv2.line(image, pts[a], pts[b], color, 2)
                for p in pts:
                    cv2.circle(image, p, 3, color, -1)
                hx0, hy0, hx1, hy1 = hand_box(hand.landmarks, w, h)
                cv2.rectangle(image, (hx0, hy0), (hx1, hy1), color, 2)
                text = "" if face is not None else short_id(pid) + "  "
                fill = GREY
                if match is not None:
                    score = "--" if match.score is None else f"{match.score:.2f}"
                    text += f"{match.activity_id} {score}"
                    fill = score_color(match.activity_id, match.score)
                labels.append((text.strip() or short_id(pid), hx0, hy0, fill))

        for text, x, y, fill in labels:
            label(image, text, x, y, fill)


def create_stage() -> OverlayStage:
    return OverlayStage()
