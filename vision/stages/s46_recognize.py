"""Recognise mode: which gesture is each person doing? (display only)

Runs only when CUES_MODE=recognize. For each person, on every frame:

1. Score every gesture in vision.mode.RECOGNIZE_SET: gesture tasks against
   their recorded examples (best hand), raise_hand from the pose.
2. The candidate is the gesture with the highest score, if that score is at
   or above that gesture's own success threshold; otherwise "no gesture".
3. Hysteresis: a new candidate must stay the candidate for SWITCH_SECONDS
   before it replaces the shown gesture. This stops the label flickering when
   two scores are close or a score dips for a frame.

Writes ctx["recognized"] = {person_id: Recognized(activity_id or None, score,
hand)}. Nothing here changes seat_state, status or events.
"""

from __future__ import annotations

from dataclasses import dataclass

from vision import activities, mode
from vision.gestures.normalize import normalize
from vision.grouping import GROUPING
from vision.perception import Hand
from vision.stages.s30_gestures import MatcherCache
from vision.stages.s35_raise_hand import highest_hand, raise_confidence

SWITCH_SECONDS = 0.5


@dataclass
class Recognized:
    activity_id: str | None  # None = no gesture recognised
    score: float | None
    hand: Hand | None


def score_gestures(pid: str, ctx: dict, cache: MatcherCache, gesture_ids) -> dict:
    """{activity_id: (score or None, hand or None)} for each gesture in the set."""
    hands = ctx.get("hands", {}).get(pid, [])
    person = ctx.get("people", {}).get(pid)
    out = {}
    for aid in gesture_ids:
        activity = activities.get(aid)
        if activity.check_type == "gesture":
            matcher, _ = cache.get(aid)
            if matcher is None or not hands:
                out[aid] = (None, None)
                continue
            best = max(
                ((matcher.score(normalize(h.landmarks, h.handedness)), h) for h in hands),
                key=lambda item: item[0],
            )
            out[aid] = best
        elif aid == "raise_hand":
            score = raise_confidence(person)[0] if person is not None else None
            out[aid] = (score, highest_hand(hands))
    return out


def candidate(scores: dict) -> tuple[str | None, float | None]:
    """Highest-scoring gesture that clears its own success threshold, else (None, None)."""
    best_id, best_score = None, None
    for aid, (score, _) in scores.items():
        if score is None or score < activities.get(aid).success_threshold:
            continue
        if best_score is None or score > best_score:
            best_id, best_score = aid, score
    return best_id, best_score


class Recognizer:
    """Per-person hysteresis between candidate gestures."""

    def __init__(self, switch_seconds: float = SWITCH_SECONDS) -> None:
        self.switch_seconds = switch_seconds
        self.shown: str | None = None
        self._pending: str | None = None
        self._pending_since: float | None = None

    def update(self, t: float, cand: str | None) -> str | None:
        if cand == self.shown:
            self._pending = None
            return self.shown
        if cand != self._pending:
            self._pending, self._pending_since = cand, t
        if t - self._pending_since >= self.switch_seconds:
            self.shown, self._pending = cand, None
        return self.shown


class RecognizeStage:
    name = "recognize"
    rate_hz = None

    def __init__(
        self,
        grouping=GROUPING,
        cache: MatcherCache | None = None,
        gesture_ids=mode.RECOGNIZE_SET,
        enabled=None,
    ) -> None:
        self.grouping = grouping
        self.cache = cache or MatcherCache()
        self.gesture_ids = tuple(gesture_ids)
        self.enabled = mode.recognizing() if enabled is None else enabled
        self._recognizers: dict[str, Recognizer] = {}

    def process(self, frame, ctx) -> None:
        if not self.enabled:
            return
        result = {}
        live = self.grouping.ids(ctx)
        for pid in live:
            scores = score_gestures(pid, ctx, self.cache, self.gesture_ids)
            cand, _ = candidate(scores)
            shown = self._recognizers.setdefault(pid, Recognizer()).update(frame.timestamp, cand)
            if shown is None:
                hands = ctx.get("hands", {}).get(pid, [])
                result[pid] = Recognized(None, None, highest_hand(hands))
            else:
                score, hand = scores[shown]
                result[pid] = Recognized(shown, score, hand)
        for gone in [p for p in self._recognizers if p not in live]:
            del self._recognizers[gone]
        ctx["recognized"] = result

    def draw(self, image, ctx) -> None:
        """Drawn by s90_overlay."""


def create_stage() -> RecognizeStage:
    for aid in mode.RECOGNIZE_SET:
        activities.get(aid)  # fail fast on a typo in RECOGNIZE_SET
    return RecognizeStage()
