"""Gesture detection: which known gesture is each person doing? (display only)

Always runs (with the vision.gestures flag), alongside each person's assigned
task. For each person, on every frame:

1. Score every activity in vision/activities.json (thumbs_up, raise_hand,
   recorded custom gestures; raise_hand only while vision.raise_hand is on),
   with hand-shape rules so gestures cannot both be true:
   * raise_hand: the pose-based raise confidence, but only if the raised hand
     is an open palm facing the camera (hand_pose.open_palm_facing).
     A raised thumbs-up or fist scores 0.
   * thumbs_up: the MediaPipe Gesture Recognizer's Thumb_Up score.
   * recorded gestures: the best hand against the teacher's examples,
     skipping hands whose palm faces the camera. A gesture with no recorded
     examples is skipped.
2. The candidate is the gesture with the highest score, if that score is at
   or above that gesture's own success threshold; otherwise "no gesture".
3. Hysteresis: a new candidate must stay the candidate for SWITCH_SECONDS
   before it replaces the shown gesture. This stops the label flickering when
   two scores are close or a score dips for a frame.

Writes ctx["recognized"] = {person_id: Recognized(activity_id or None, score,
hand)}; the overlay shows a completed gesture in green. Nothing here changes
seat_state, status or events: those follow the assigned task.
"""

from __future__ import annotations

from dataclasses import dataclass

from vision import activities, flags
from vision.gestures.hand_pose import open_palm_facing
from vision.grouping import GROUPING
from vision.perception import Hand
from vision.stages.s30_gestures import MatcherCache, score_gesture
from vision.stages.s35_raise_hand import highest_hand, raise_confidence

FLAG = "vision.gestures"
SWITCH_SECONDS = 0.5
# A shown gesture stays up this long after it stops being the candidate, so a
# flickering hand detection does not make the green label blink off.
CLEAR_SECONDS = 1.5


@dataclass
class Recognized:
    activity_id: str | None  # None = no gesture recognised
    score: float | None
    hand: Hand | None


def all_gesture_ids() -> tuple[str, ...]:
    """Every activity to detect: all of activities.json, raise_hand only if its flag is on."""
    ids = []
    for activity in activities.load_activities().values():
        if activity.check_type == "gesture":
            ids.append(activity.id)
        elif activity.id == "raise_hand" and flags.enabled("vision.raise_hand"):
            ids.append(activity.id)
    return tuple(ids)


def score_gestures(pid: str, ctx: dict, cache: MatcherCache, gesture_ids) -> dict:
    """{activity_id: (score or None, hand or None)} for each gesture in the set."""
    hands = ctx.get("hands", {}).get(pid, [])
    person = ctx.get("people", {}).get(pid)
    out = {}
    for aid in gesture_ids:
        activity = activities.get(aid)
        if activity.check_type == "gesture":
            # Recorded gestures skip palm-facing hands; built-in ones (Thumb_Up)
            # rely on the recogniser, which already tells palm from thumbs-up.
            score, hand, _, _ = score_gesture(activity, hands, cache, exclude_palm=True)
            out[aid] = (score, hand)
        elif aid == "raise_hand":
            hand = highest_hand(hands)
            if person is None:
                out[aid] = (None, hand)
                continue
            score = raise_confidence(person)[0]
            # A raised hand only counts as an open palm facing the camera.
            out[aid] = (score if open_palm_facing(hand) else 0.0, hand)
    return out


# When both are completed, the more specific gesture wins: a raised open palm
# is a raised hand, not just an open palm.
PREFERRED_OVER = {"raise_hand": ("open_palm",)}


def candidate(scores: dict) -> tuple[str | None, float | None]:
    """Highest-scoring gesture that clears its own success threshold, else (None, None)."""
    passed = {
        aid: score
        for aid, (score, _) in scores.items()
        if score is not None and score >= activities.get(aid).success_threshold
    }
    for winner, losers in PREFERRED_OVER.items():
        if winner in passed:
            for loser in losers:
                passed.pop(loser, None)
    if not passed:
        return None, None
    best_id = max(passed, key=passed.get)
    return best_id, passed[best_id]


class Recognizer:
    """Per-person hysteresis between candidate gestures."""

    def __init__(
        self, switch_seconds: float = SWITCH_SECONDS, clear_seconds: float = CLEAR_SECONDS
    ) -> None:
        self.switch_seconds = switch_seconds
        self.clear_seconds = clear_seconds
        self.shown: str | None = None
        self._pending: str | None = None  # meaningful only while _pending_since is set
        self._pending_since: float | None = None

    def update(self, t: float, cand: str | None) -> str | None:
        """Show cand only after it has been the candidate for switch_seconds.

        "No gesture" (cand None) is a candidate like any other, so a one-frame
        dip does not clear the label either.
        """
        if cand == self.shown:
            self._pending_since = None
            return self.shown
        if self._pending_since is None or cand != self._pending:
            self._pending, self._pending_since = cand, t
        needed = self.clear_seconds if cand is None else self.switch_seconds
        if t - self._pending_since >= needed:
            self.shown, self._pending_since = cand, None
        return self.shown


class RecognizeStage:
    name = "recognize"
    rate_hz = None

    def __init__(
        self,
        grouping=GROUPING,
        cache: MatcherCache | None = None,
        gesture_ids=None,
    ) -> None:
        self.grouping = grouping
        self.cache = cache or MatcherCache()
        # None = follow the catalog live, so gestures created from the dashboard
        # are detected without a restart.
        self._fixed_ids = tuple(gesture_ids) if gesture_ids is not None else None
        self._recognizers: dict[str, Recognizer] = {}

    @property
    def gesture_ids(self) -> tuple[str, ...]:
        return self._fixed_ids if self._fixed_ids is not None else all_gesture_ids()

    def process(self, frame, ctx) -> None:
        result = {}
        live = self.grouping.ids(ctx)
        ids = self.gesture_ids
        for pid in live:
            scores = score_gestures(pid, ctx, self.cache, ids)
            cand, _ = candidate(scores)
            shown = self._recognizers.setdefault(pid, Recognizer()).update(frame.timestamp, cand)
            if shown is None:
                hands = ctx.get("hands", {}).get(pid, [])
                result[pid] = Recognized(None, None, highest_hand(hands))
            else:
                # The score and hand are always the live ones: while a completed gesture
                # is held through a dip, the number keeps falling with the hand
                # instead of freezing and then jumping, and the skeleton follows the
                # real hand. (score is None when no hand is in view.)
                score, hand = scores[shown]
                hand = hand or highest_hand(ctx.get("hands", {}).get(pid, []))
                result[pid] = Recognized(shown, score, hand)
        for gone in [p for p in self._recognizers if p not in live]:
            del self._recognizers[gone]
        ctx["recognized"] = result

    def draw(self, image, ctx) -> None:
        """Drawn by s90_overlay."""


def create_stage() -> RecognizeStage:
    return RecognizeStage()
