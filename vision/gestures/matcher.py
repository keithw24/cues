"""Nearest-neighbour gesture matcher with a per-activity match score.

For a new hand vector v:

    d_target = distance to the nearest recorded target example
    d_rest   = distance to the nearest recorded rest example (if any)

    score = clamp(1 - d_target / rejection_threshold, 0, 1)
    if d_rest < d_target:  score *= d_rest / d_target   # closer to "rest"

The score is a match score, not a probability: it says how close the hand is
to the teacher's examples.

The rejection threshold is calibrated from the examples themselves. For each
target example we measure the distance to its nearest other example; the
average of those is how far a genuine attempt typically lands from the
nearest example. The threshold is SCALE times that, so a typical genuine
attempt scores about 1 - 1/SCALE (0.83 with SCALE = 6). A floor stops a few
near-identical examples from making it impossibly strict. Each activity's
success / review thresholds are applied elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vision.gestures.templates import Templates

MIN_REJECTION = 0.5
SCALE = 6.0


def calibrate_rejection(target: np.ndarray, floor: float = MIN_REJECTION) -> float:
    """SCALE x mean nearest-other-example distance among targets, at least `floor`."""
    if len(target) < 2:
        return floor
    dists = np.linalg.norm(target[:, None, :] - target[None, :, :], axis=-1)
    np.fill_diagonal(dists, np.inf)
    typical = float(dists.min(axis=1).mean())
    return max(floor, SCALE * typical)


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
        threshold = rejection if rejection is not None else calibrate_rejection(target)
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
