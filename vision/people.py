"""People mode: find each person, box them, and keep their id between frames.

Vision groups everything by person (there is no fixed-seat mode):

1. MediaPipe Pose Landmarker finds up to MAX_PEOPLE people. Each person comes
   with 33 body points (nose, shoulders, wrists, ...) and a visibility value
   per point.
2. Each person gets a box around their visible upper-body points, with
   padding, smoothed over frames.
3. PersonTracker matches each box to a box from earlier frames, so a person
   keeps the same id (S1-P1, S1-P2, ...) while they stay roughly in place. This
   is position tracking only: nothing about who the person is is stored, and
   there is no face recognition.
4. PeopleGrouping assigns MediaPipe hands and faces to the person they belong
   to, so the later stages (gestures, raise-hand, expression, status) work per
   person exactly as they worked per seat.

An id stays "live" for RELEASE_SECONDS after the person was last seen, so the
status stage can report tracking_lost for them. After that the id is released
and can be reused.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from vision.camera import ASPECT

MAX_PEOPLE = 4
RELEASE_SECONDS = 10.0
MIN_IOU = 0.2
MAX_RELATIVE_JUMP = 0.6  # centre may move up to 0.6 x the box size between matches
BOX_PADDING = 0.15
MIN_VISIBILITY = 0.5
MIN_UPPER_POINTS = 4
UPPER_BODY = list(range(0, 17))  # nose, eyes, ears, mouth, shoulders, elbows, wrists
SMOOTHING = 0.4  # weight of the new box; the rest comes from the previous box
MISS_GRACE_SECONDS = 0.5  # keep showing a person this long after a missed frame

# MediaPipe Pose landmark indices.
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_WRIST, RIGHT_WRIST = 15, 16

PERSON_COLORS = [(255, 160, 0), (0, 200, 255), (200, 0, 200), (0, 220, 120)]


@dataclass
class Person:
    id: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1, normalised 0-1
    landmarks: np.ndarray  # (33, 4): x, y, z, visibility

    def point(self, index: int) -> tuple[float, float, float]:
        x, y, _, vis = self.landmarks[index]
        return float(x), float(y), float(vis)

    @property
    def shoulder_width(self) -> float:
        lx, ly, _ = self.point(LEFT_SHOULDER)
        rx, ry, _ = self.point(RIGHT_SHOULDER)
        # In units of frame height: x is converted by the frame's aspect ratio.
        return float(np.hypot((lx - rx) * ASPECT, ly - ry))


def person_color(person_id: str) -> tuple[int, int, int]:
    try:
        n = int(person_id.rsplit("P", 1)[1])
    except (IndexError, ValueError):
        return (200, 200, 200)
    return PERSON_COLORS[(n - 1) % len(PERSON_COLORS)]


def box_from_landmarks(landmarks: np.ndarray, pad: float = BOX_PADDING):
    """Box around the visible upper-body points, padded and clipped to the frame.

    Only points 0-16 (face, shoulders, elbows, wrists) are used. Seated
    children's hips and legs are usually hidden, and MediaPipe guesses those
    points, which made the box change size from frame to frame. Returns None
    when fewer than MIN_UPPER_POINTS upper-body points are visible.
    """
    upper = landmarks[UPPER_BODY]
    visible = upper[upper[:, 3] >= MIN_VISIBILITY]
    if len(visible) < MIN_UPPER_POINTS:
        return None
    x0, y0 = visible[:, 0].min(), visible[:, 1].min()
    x1, y1 = visible[:, 0].max(), visible[:, 1].max()
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    return (
        float(max(0.0, x0 - px)),
        float(max(0.0, y0 - py)),
        float(min(1.0, x1 + px)),
        float(min(1.0, y1 + py)),
    )


def iou(a, b) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def centre(box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


@dataclass
class _Track:
    id: str
    box: tuple[float, float, float, float]  # smoothed
    landmarks: np.ndarray
    last_seen: float


@dataclass
class PersonTracker:
    """Keeps a stable id per person across frames.

    On each frame:
    1. Drop tracks not seen for release_seconds (their id can be reused).
    2. Build an upper-body box for each detected pose; skip unreliable poses.
    3. Match boxes to existing tracks: boxes that overlap (IoU >= MIN_IOU), or
       whose centre moved less than MAX_RELATIVE_JUMP x the box size. The best
       pairs are matched first; each track and box is used at most once.
    4. Smooth each matched box with the previous one (SMOOTHING), so the box
       does not jitter.
    5. Unmatched boxes get the lowest free id.
    6. Return the people seen now, plus people missed for less than
       MISS_GRACE_SECONDS (shown at their last position), so one missed frame
       does not make a person vanish.
    """

    station_id: str = "S1"
    release_seconds: float = RELEASE_SECONDS
    tracks: dict[str, _Track] = field(default_factory=dict)

    def update(self, t: float, detections: list[np.ndarray]) -> dict[str, Person]:
        limit = self.release_seconds
        expired = [tid for tid, tr in self.tracks.items() if t - tr.last_seen > limit]
        for tid in expired:
            del self.tracks[tid]

        found = [(lm, box) for lm in detections if (box := box_from_landmarks(lm)) is not None]
        pairs = []  # (cost, track id, detection index); lower cost = better match
        for tid, track in self.tracks.items():
            size = max(track.box[2] - track.box[0], track.box[3] - track.box[1], 1e-3)
            for i, (_, box) in enumerate(found):
                overlap = iou(track.box, box)
                (cx0, cy0), (cx1, cy1) = centre(track.box), centre(box)
                jump = float(np.hypot(cx1 - cx0, cy1 - cy0)) / size
                if overlap >= MIN_IOU or jump <= MAX_RELATIVE_JUMP:
                    pairs.append((jump - overlap, tid, i))
        assigned: dict[int, str] = {}
        used: set[str] = set()
        for _, tid, i in sorted(pairs):
            if tid not in used and i not in assigned:
                assigned[i] = tid
                used.add(tid)

        for i, (landmarks, box) in enumerate(found):
            tid = assigned.get(i)
            if tid is not None:
                old = self.tracks[tid].box
                pairs_xy = zip(box, old, strict=True)
                box = tuple(SMOOTHING * n + (1 - SMOOTHING) * o for n, o in pairs_xy)
            else:
                tid = self._new_id()
                if tid is None:
                    continue  # already tracking MAX_PEOPLE ids
            self.tracks[tid] = _Track(tid, box, landmarks, t)

        return {
            tid: Person(tid, tr.box, tr.landmarks)
            for tid, tr in self.tracks.items()
            if t - tr.last_seen <= MISS_GRACE_SECONDS
        }

    @property
    def live_ids(self) -> list[str]:
        return sorted(self.tracks, key=lambda tid: int(tid.rsplit("P", 1)[1]))

    def _new_id(self) -> str | None:
        for n in range(1, MAX_PEOPLE + 1):
            tid = f"{self.station_id}-P{n}"
            if tid not in self.tracks:
                return tid
        return None


class PeopleGrouping:
    """Assigns hands and faces to tracked people. Same interface as SeatZones."""

    mode = "people"

    def __init__(self, station_id: str = "S1") -> None:
        self.station_id = station_id

    def ids(self, ctx) -> list[str]:
        return list(ctx.get("person_ids", []))

    def hand_owner(self, hand_points: np.ndarray, ctx) -> str | None:
        """The person whose pose wrist is closest to this hand's wrist."""
        hx, hy = float(hand_points[0, 0]), float(hand_points[0, 1])
        best, best_d = None, None
        for pid, person in ctx.get("people", {}).items():
            limit = max(person.shoulder_width, 0.05)  # reach scales with body size
            for wrist in (LEFT_WRIST, RIGHT_WRIST):
                wx, wy, _ = person.point(wrist)
                d = float(np.hypot((wx - hx) * ASPECT, wy - hy))
                if d <= limit and (best_d is None or d < best_d):
                    best, best_d = pid, d
        if best is not None:
            return best
        return self._inside_box(hx, hy, ctx)

    def face_owner(self, cx: float, cy: float, box, ctx) -> str | None:
        """The person whose pose nose is inside this face box (normalised)."""
        x0, y0, x1, y1 = box
        for pid, person in ctx.get("people", {}).items():
            nx, ny, _ = person.point(NOSE)
            if x0 <= nx <= x1 and y0 <= ny <= y1:
                return pid
        return self._inside_box(cx, cy, ctx)

    def anchor(self, seat_id: str, ctx, w: int, h: int, row: int = 0) -> tuple[int, int] | None:
        """Where to draw text for this person: inside the top of their box."""
        person = ctx.get("people", {}).get(seat_id)
        if person is None:
            return None
        return int(person.box[0] * w) + 6, int(person.box[1] * h) + 20 + 22 * row

    def color(self, seat_id: str) -> tuple[int, int, int]:
        return person_color(seat_id)

    @staticmethod
    def _inside_box(x: float, y: float, ctx) -> str | None:
        for pid, person in ctx.get("people", {}).items():
            x0, y0, x1, y1 = person.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                return pid
        return None


def grouping_from_env() -> PeopleGrouping:
    """The service always groups by person (the fixed-seat mode was removed)."""
    return PeopleGrouping(os.environ.get("CUES_STATION_ID", "S1"))
