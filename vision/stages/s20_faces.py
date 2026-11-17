"""Face crop per person, built from that person's tracked pose head points.

The pose model (s05_people) already finds each person's nose, eyes, ears and
mouth corners and keeps them with that person's id. The face box comes from
those points, so:

- there is no separate face detector and no face-to-person matching: a face can
  never be given to the wrong person, and a person's face is always their own;
- the box is steadied with a One Euro filter (centre, size and tilt), so a
  child who sits still gets the same crop frame after frame, while a child who
  moves is followed with little lag;
- the crop is turned upright using the eye line, which suits the expression
  model better than a tilted face.

Writes ctx["faces"] = {person_id: Face}. A person whose eyes or nose are not
visible (turned away, hidden) gets no face, so expression is not run for them.
No face recognition: faces are only located from body points, never identified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from vision.people import MIN_VISIBILITY
from vision.people import person_color as seat_color
from vision.perception import Face

# MediaPipe Pose landmark indices (left/right are the person's own).
NOSE = 0
LEFT_EYE, RIGHT_EYE = 2, 5
LEFT_EAR, RIGHT_EAR = 7, 8
MOUTH_LEFT, MOUTH_RIGHT = 9, 10

# Face size from the head points, as multiples of each distance. Several are
# measured and the largest wins, because turning the head shrinks the
# side-to-side distances (eyes, ears) but not eyes-to-mouth.
SIDE_PER_EYE_DISTANCE = 2.6
SIDE_PER_EAR_DISTANCE = 1.15
SIDE_PER_EYE_TO_MOUTH = 2.5
CENTRE_BELOW_EYES = 0.12  # the face centre sits this far (x side) below the eye line
MIN_SIDE_PX = 24  # smaller than this is too few pixels to say anything about
CROP_PX = 224  # the expression model's own input size
FORGET_SECONDS = 0.5  # after this long without a face, start the filter afresh


class OneEuro:
    """One Euro filter (Casiez et al. 2012) for one value.

    Strong smoothing while the value is steady, little lag while it moves fast:
    the cut-off frequency rises with the speed of change.
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.value: float | None = None
        self.speed = 0.0
        self.t: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self.value is None or self.t is None or t <= self.t:
            self.value, self.t = x, t
            return x
        dt = t - self.t
        speed = (x - self.value) / dt
        self.speed += self._alpha(self.d_cutoff, dt) * (speed - self.speed)
        cutoff = self.min_cutoff + self.beta * abs(self.speed)
        self.value += self._alpha(cutoff, dt) * (x - self.value)
        self.t = t
        return self.value


@dataclass
class HeadPose:
    """Where the face is, in pixels: centre, square side and tilt (radians)."""

    cx: float
    cy: float
    side: float
    angle: float


def head_from_landmarks(landmarks: np.ndarray, w: int, h: int) -> HeadPose | None:
    """The face square for one person, or None when their eyes or nose are not visible."""

    def point(i: int) -> np.ndarray | None:
        x, y, _, vis = landmarks[i]
        return np.array([x * w, y * h]) if vis >= MIN_VISIBILITY else None

    nose, left_eye, right_eye = point(NOSE), point(LEFT_EYE), point(RIGHT_EYE)
    if nose is None or left_eye is None or right_eye is None:
        return None
    eyes = left_eye - right_eye  # points across the face, image-right for a frontal face
    eye_distance = float(np.hypot(*eyes))
    side = SIDE_PER_EYE_DISTANCE * eye_distance
    left_ear, right_ear = point(LEFT_EAR), point(RIGHT_EAR)
    if left_ear is not None and right_ear is not None:
        side = max(side, SIDE_PER_EAR_DISTANCE * float(np.hypot(*(left_ear - right_ear))))
    eye_mid = (left_eye + right_eye) / 2
    mouth_left, mouth_right = point(MOUTH_LEFT), point(MOUTH_RIGHT)
    if mouth_left is not None and mouth_right is not None:
        mouth_mid = (mouth_left + mouth_right) / 2
        side = max(side, SIDE_PER_EYE_TO_MOUTH * float(np.hypot(*(mouth_mid - eye_mid))))
    if side < MIN_SIDE_PX:
        return None
    angle = math.atan2(eyes[1], eyes[0])
    # "Down" for this face: perpendicular to the eye line, towards the chin.
    down = np.array([-math.sin(angle), math.cos(angle)])
    centre = eye_mid + down * CENTRE_BELOW_EYES * side
    return HeadPose(float(centre[0]), float(centre[1]), side, angle)


class HeadFilter:
    """One Euro filters for one person's face square."""

    def __init__(self) -> None:
        # Tuned on pose head points with about 3 px of noise: a still child's crop
        # moves under 1 px, a child who moves 96 px is followed within 1 px after
        # 0.2 s. The size changes only as a child leans in or out, so it is
        # smoothed hardest (it takes about a second to settle after a lean).
        # Angle is in radians, so it has a larger beta.
        self.cx = OneEuro(min_cutoff=0.5, beta=0.01)
        self.cy = OneEuro(min_cutoff=0.5, beta=0.01)
        self.side = OneEuro(min_cutoff=0.1, beta=0.002)
        self.angle = OneEuro(min_cutoff=0.5, beta=0.5)
        self.last_seen = -math.inf

    def __call__(self, head: HeadPose, t: float) -> HeadPose:
        self.last_seen = t
        return HeadPose(
            self.cx(head.cx, t),
            self.cy(head.cy, t),
            self.side(head.side, t),
            self.angle(head.angle, t),
        )


def upright_crop(rgb: np.ndarray, head: HeadPose, size: int = CROP_PX) -> np.ndarray:
    """The face square, rotated so the eyes are level, as a size x size RGB image."""
    matrix = cv2.getRotationMatrix2D((head.cx, head.cy), math.degrees(head.angle), size / head.side)
    matrix[0, 2] += size / 2 - head.cx
    matrix[1, 2] += size / 2 - head.cy
    return cv2.warpAffine(
        rgb, matrix, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )


def square_box(head: HeadPose, w: int, h: int) -> tuple[int, int, int, int]:
    """The axis-aligned box around the face square, in pixels, clipped to the frame."""
    half = head.side / 2
    return (
        max(0, int(head.cx - half)),
        max(0, int(head.cy - half)),
        min(w, int(head.cx + half)),
        min(h, int(head.cy + half)),
    )


class FacesStage:
    name = "faces"
    rate_hz = None  # every frame: the filter needs every pose update to stay steady

    def __init__(self) -> None:
        self._filters: dict[str, HeadFilter] = {}

    def load(self) -> None:
        """Nothing to load: the face comes from the pose model's points."""

    def faces(self, rgb: np.ndarray, people: dict, t: float) -> dict[str, Face]:
        h, w = rgb.shape[:2]
        result: dict[str, Face] = {}
        for pid, person in people.items():
            raw = head_from_landmarks(person.landmarks, w, h)
            if raw is None:
                continue
            filt = self._filters.get(pid)
            if filt is None or t - filt.last_seen > FORGET_SECONDS:
                filt = self._filters[pid] = HeadFilter()
            head = filt(raw, t)
            result[pid] = Face(square_box(head, w, h), upright_crop(rgb, head), pid)
        # People who left: their filters go too, so a reused id starts afresh.
        for pid in [p for p, f in self._filters.items() if t - f.last_seen > FORGET_SECONDS]:
            del self._filters[pid]
        return result

    def process(self, frame, ctx) -> None:
        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        ctx["faces"] = self.faces(rgb, ctx.get("people", {}), frame.timestamp)

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if not overlay.debug():
            return
        for seat, face in ctx.get("faces", {}).items():
            x0, y0, x1, y1 = face.box
            cv2.rectangle(image, (x0, y0), (x1, y1), seat_color(seat), 2)


def create_stage() -> FacesStage:
    return FacesStage()
