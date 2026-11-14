"""Turn 21 MediaPipe hand landmarks into a 63-number vector for matching.

The vector should change when the hand shape changes, and not when the hand
moves around the frame, gets closer to the camera, or is a left hand instead of
a right hand. Steps:

1. Move the wrist (landmark 0) to the origin.
2. Divide by hand size: the LARGEST x-y distance between any two palm points
   (wrist and the four finger knuckles: 0, 5, 9, 13, 17).
   A single distance (e.g. wrist to middle knuckle) can look tiny when the
   hand is turned, as in a thumbs-up seen from the back, and dividing by it
   blew the values up. The largest palm distance stays reasonable from any
   angle: if the wrist and knuckles line up, the palm width still shows.
3. Mirror left hands (flip x) so both hands look like right hands.
4. Flatten to 63 numbers (21 points x 3 coordinates).

is_reliable() rejects vectors whose values are still extreme (a hand seen
almost exactly end-on, or a bad detection); the recorder does not save them.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

WRIST = 0
PALM_POINTS = (0, 5, 9, 13, 17)
VECTOR_SIZE = 63
MAX_COORD = 4.0  # normal hands stay within about +-2.5 hand sizes


def hand_size(points: np.ndarray) -> float:
    return max(
        float(np.linalg.norm(points[a, :2] - points[b, :2]))
        for a, b in combinations(PALM_POINTS, 2)
    )


def normalize(landmarks: np.ndarray, handedness: str = "Right") -> np.ndarray:
    points = np.asarray(landmarks, dtype=np.float64).reshape(21, 3).copy()
    points -= points[WRIST]
    size = hand_size(points)
    if size < 1e-6:
        raise ValueError("hand too small or landmarks degenerate")
    points /= size
    if handedness.lower() == "left":
        points[:, 0] *= -1
    return points.reshape(VECTOR_SIZE)


def is_reliable(vector: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(vector)) and np.abs(vector).max() <= MAX_COORD)
