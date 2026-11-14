"""Which side of a hand faces the camera, and whether the hand is open.

Both come from the 21 MediaPipe hand landmarks; no extra model.

Palm or back (palm_side):
    Take two vectors from the wrist: to the index-finger knuckle (point 5) and
    to the little-finger knuckle (point 17). The sign of their 2-D cross
    product says which way the hand turns from index to little finger, and so
    which side faces the camera, once you know if it is a left or right hand.
    The sign does not change when the hand tilts in the image, so a tilted
    raised hand or thumbs-up still reads correctly. When the hand is seen
    edge-on (the two vectors nearly in line) the result is "side".

    MediaPipe labels handedness assuming a mirrored (selfie) image. Vision
    passes the camera picture unmirrored, so a MediaPipe "Left" is the
    person's right hand. If palm and back come out swapped on a particular
    camera (for example one that mirrors its own output), set
    CUES_PALM_FLIP=1.

Open hand (is_open):
    A finger is extended when its tip is clearly further from the wrist than
    its knuckle (ratio >= EXTENDED_RATIO). The hand is open when at least
    MIN_EXTENDED of the four fingers (index to little) are extended. The thumb
    is not counted.
"""

from __future__ import annotations

import os

import numpy as np

WRIST, INDEX_MCP, PINKY_MCP = 0, 5, 17
FINGERS = ((5, 8), (9, 12), (13, 16), (17, 20))  # (knuckle, tip): index..little
EXTENDED_RATIO = 1.6
MIN_EXTENDED = 3
SIDE_SINE = 0.25  # below this |sin(angle)|, the hand is seen edge-on


def palm_side(landmarks: np.ndarray, handedness: str) -> str:
    """'palm', 'back' or 'side': which side of the hand faces the camera."""
    pts = np.asarray(landmarks, dtype=np.float64)[:, :2]
    v1, v2 = pts[INDEX_MCP] - pts[WRIST], pts[PINKY_MCP] - pts[WRIST]
    norm = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if norm < 1e-9:
        return "side"
    sine = float(v1[0] * v2[1] - v1[1] * v2[0]) / norm
    if abs(sine) < SIDE_SINE:
        return "side"
    # In image coordinates (y down), the person's right hand with the palm to
    # the camera gives a negative sine. MediaPipe's "Left" = the person's right.
    persons_right = handedness.lower() == "left"
    palm = (sine < 0) if persons_right else (sine > 0)
    if os.environ.get("CUES_PALM_FLIP", "0") in ("1", "true"):
        palm = not palm
    return "palm" if palm else "back"


def extended_fingers(landmarks: np.ndarray) -> int:
    pts = np.asarray(landmarks, dtype=np.float64)[:, :2]
    count = 0
    for knuckle, tip in FINGERS:
        k = np.linalg.norm(pts[knuckle] - pts[WRIST])
        if k > 1e-9 and np.linalg.norm(pts[tip] - pts[WRIST]) / k >= EXTENDED_RATIO:
            count += 1
    return count


def is_open(landmarks: np.ndarray) -> bool:
    return extended_fingers(landmarks) >= MIN_EXTENDED


def describe(landmarks: np.ndarray, handedness: str) -> str:
    """Short text for debugging, e.g. 'palm, open (4/4 fingers)'."""
    n = extended_fingers(landmarks)
    state = "open" if n >= MIN_EXTENDED else "closed"
    return f"{palm_side(landmarks, handedness)}, {state} ({n}/4 fingers)"
