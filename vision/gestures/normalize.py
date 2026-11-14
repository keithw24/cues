"""Turn 21 MediaPipe hand landmarks into a 63-number vector for matching.

The vector should change when the hand shape changes, and not when the hand
moves around the frame, gets closer to the camera, or is a left hand instead of
a right hand. Steps:

1. Move the wrist (landmark 0) to the origin.
2. Divide by hand size: the distance from the wrist to the middle-finger
   knuckle (landmark 9), measured in x and y.
3. Mirror left hands (flip x) so both hands look like right hands.
4. Flatten to 63 numbers (21 points x 3 coordinates).
"""

from __future__ import annotations

import numpy as np

WRIST = 0
MIDDLE_MCP = 9
VECTOR_SIZE = 63


def normalize(landmarks: np.ndarray, handedness: str = "Right") -> np.ndarray:
    points = np.asarray(landmarks, dtype=np.float64).reshape(21, 3).copy()
    points -= points[WRIST]
    size = float(np.linalg.norm(points[MIDDLE_MCP, :2]))
    if size < 1e-6:
        raise ValueError("hand too small or landmarks degenerate")
    points /= size
    if handedness.lower() == "left":
        points[:, 0] *= -1
    return points.reshape(VECTOR_SIZE)
