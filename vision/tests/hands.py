"""Realistic synthetic MediaPipe hands for tests (normalised image coordinates).

The person's right hand, as an unmirrored camera sees it; MediaPipe labels it
"Left". s = hand size.
"""

import numpy as np

PERSONS_RIGHT = "Left"  # MediaPipe's label for the person's right hand (unmirrored image)


def _hand(cx, cy, s, knuckle_xs, tip_reach, thumb_tip):
    pts = np.zeros((21, 3), np.float32)
    pts[0] = (cx, cy, 0)  # wrist
    for i, (kx, reach) in enumerate(zip(knuckle_xs, tip_reach, strict=True)):
        k = 5 + 4 * i  # 5, 9, 13, 17: knuckles
        knuckle = np.array([cx + kx * s, cy - 1.0 * s])
        tip = np.array([cx + kx * s, cy - reach * s])
        for j, f in enumerate((0.0, 0.45, 0.75, 1.0)):
            pts[k + j, :2] = knuckle + f * (tip - knuckle)
    pts[1:5, :2] = np.linspace([cx, cy], thumb_tip, 5)[1:]
    return pts


def open_palm(cx=0.3, cy=0.3, s=0.06):
    """Fingers up and spread, palm to the camera: index on the camera's right."""
    return _hand(
        cx, cy, s, (0.3, 0.1, -0.1, -0.3), (2.0, 2.1, 2.0, 1.8), (cx + 0.7 * s, cy - 0.4 * s)
    )


def thumbs_up_back(cx=0.3, cy=0.6, s=0.06):
    """Fingers curled, back of the hand to the camera: index on the camera's left."""
    return _hand(
        cx, cy, s, (-0.3, -0.1, 0.1, 0.3), (1.2, 1.2, 1.15, 1.1), (cx - 0.35 * s, cy - 2.0 * s)
    )
