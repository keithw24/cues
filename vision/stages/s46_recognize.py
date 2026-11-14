"""Recognise mode: which gesture is each person doing? (display only)

Runs only when CUES_MODE=recognize. For each person, on every frame:

1. Score every gesture in vision.mode.RECOGNIZE_SET, with hand-shape rules so
   the two gestures cannot both be true:
   * raise_hand: the pose-based raise confidence, but only if the raised hand
     is an open palm facing the camera (recogniser's Open_Palm + palm side).
     A raised thumbs-up or fist scores 0.
   * thumbs_up: the MediaPipe Gesture Recognizer's Thumb_Up score.
   * recorded gestures: the best hand against the teacher's examples,
     skipping hands whose palm faces the camera.
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
from vision.gestures.hand_pose import is_open, palm_side
from vision.grouping import GROUPING
from vision.perception import Hand
from vision.stages.s30_gestures import MatcherCache, score_gesture
from vision.stages.s35_raise_hand import highest_hand, raise_confidence

SWITCH_SECONDS = 0.5
OPEN_PALM_MIN = 0.5


@dataclass
class Recognized:
    activity_id: str | None  # None = no gesture recognised
    score: float | None
    hand: Hand | None


def has_open_palm(hand) -> bool:
    """Open palm facing the camera.

    Open: the Gesture Recognizer's Open_Palm score is at least OPEN_PALM_MIN
    (finger counting is used when there are no recogniser scores). Facing:
    vision.gestures.hand_pose.palm_side.
    """
    if hand is None or palm_side(hand.landmarks, hand.handedness) != "palm":
        return False
    if hand.gestures:
        return hand.gestures.get("Open_Palm", 0.0) >= OPEN_PALM_MIN
    return is_open(hand.landmarks)


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
            out[aid] = (score if has_open_palm(hand) else 0.0, hand)
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
