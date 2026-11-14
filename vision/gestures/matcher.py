"""Nearest-neighbour gesture matcher with a per-activity match score.

For a new hand vector v:

    d_target = distance to the nearest recorded target example
    d_rest   = distance to the nearest recorded rest example (if any)

    score = clamp(1 - d_target / rejection_threshold, 0, 1)
    if d_rest < d_target:  score *= d_rest / d_target   # closer to "rest"

The score is a match score, not a probability: it says how close the hand is
to the teacher's examples.

The rejection threshold (the distance at which the score reaches 0) is
calibrated from the examples:

* Spread: the median distance between any two target examples. Frames from
  one 2-second take are almost identical, so nearest-neighbour distances
  hugely understate how much a genuine attempt varies; the median over all
  pairs reflects variation across takes.
* threshold = SCALE x spread, so an attempt as different as two typical
  examples still scores about 1 - 1/SCALE (0.8 with SCALE = 5).
* If rest examples exist, the threshold is capped at REST_CAP x the distance
  from the targets to the nearest rest example, so a rest pose always scores
  low even if the targets are spread out.
* A floor stops a few near-identical examples from making it impossibly strict.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vision.gestures.templates import Templates

MIN_REJECTION = 0.5
SCALE = 5.0
REST_CAP = 0.8


def calibrate_rejection(
    target: np.ndarray, rest: np.ndarray | None = None, floor: float = MIN_REJECTION
) -> float:
    """Distance at which the score reaches 0. See the module docstring."""
    if len(target) < 2:
        return floor
    dists = np.linalg.norm(target[:, None, :] - target[None, :, :], axis=-1)
    spread = float(np.median(dists[np.triu_indices(len(target), k=1)]))
    threshold = max(floor, SCALE * spread)
    if rest is not None and len(rest):
        gap = float(np.linalg.norm(target[:, None, :] - rest[None, :, :], axis=-1).min())
        threshold = min(threshold, max(floor, REST_CAP * gap))
    return threshold


@dataclass
class Matcher:
    activity_id: str
    target: np.ndarray
    rest: np.ndarray
    rejection_threshold: float

    @classmethod
    def from_templates(cls, templates: Templates, rejection: float | None = None) -> Matcher:
        target, rest = templates.arrays()
        if len(target) == 0:
            raise ValueError(f"no target examples recorded for {templates.activity_id!r}")
        threshold = rejection if rejection is not None else calibrate_rejection(target, rest)
        return cls(templates.activity_id, target, rest, threshold)

    def distances(self, vector: np.ndarray) -> tuple[float, float]:
        d_target = float(np.linalg.norm(self.target - vector, axis=1).min())
        d_rest = (
            float(np.linalg.norm(self.rest - vector, axis=1).min()) if len(self.rest) else np.inf
        )
        return d_target, d_rest

    def score(self, vector: np.ndarray) -> float:
        d_target, d_rest = self.distances(vector)
        score = max(0.0, min(1.0, 1.0 - d_target / self.rejection_threshold))
        if d_rest < d_target:
            score *= d_rest / d_target
        return round(score, 3)
