"""All-gestures readout: every task's score for every person, for display only.

Each person still has one assigned task, and only that task's score drives
seat_state, status and events (vision/stages/s30_gestures.py,
s35_raise_hand.py, s50_status.py). This stage adds a readout of how each
person scores on *every* known task at the same time, e.g.

    raise_hand 0.91   thumbs_up 0.12   custom_gesture_01 --

It writes ctx["all_scores"] = {person_id: {activity_id: score or None}}, which
the overlay and vision.watch show. Nothing here is sent to Supabase.

* Gesture tasks: built-in ones (thumbs_up) from the MediaPipe Gesture
  Recognizer; recorded ones against the teacher's examples. None ("--") when
  no examples are recorded or no hand is visible.
* raise_hand: the pose-based raise confidence. None when the person is not
  visible.
"""

from __future__ import annotations

from vision import activities
from vision.grouping import GROUPING
from vision.stages.s30_gestures import MatcherCache, score_gesture
from vision.stages.s35_raise_hand import raise_confidence


def all_scores_for(pid: str, ctx: dict, cache: MatcherCache) -> dict[str, float | None]:
    hands = ctx.get("hands", {}).get(pid, [])
    person = ctx.get("people", {}).get(pid)
    scores: dict[str, float | None] = {}
    for activity in activities.load_activities().values():
        if activity.check_type == "gesture":
            scores[activity.id] = score_gesture(activity, hands, cache)[0]
        elif activity.id == "raise_hand":
            scores[activity.id] = raise_confidence(person)[0] if person is not None else None
    return scores


def format_scores(scores: dict[str, float | None]) -> str:
    """'raise_hand 0.91   thumbs_up 0.12   custom_gesture_01 --'"""
    return "   ".join(f"{aid} {'--' if s is None else f'{s:.2f}'}" for aid, s in scores.items())


class AllScoresStage:
    name = "all_scores"
    rate_hz = 5.0  # a readout for people to read; no need for every frame

    def __init__(self, grouping=GROUPING, cache: MatcherCache | None = None) -> None:
        self.grouping = grouping
        self.cache = cache or MatcherCache()

    def process(self, frame, ctx) -> None:
        ctx["all_scores"] = {
            pid: all_scores_for(pid, ctx, self.cache) for pid in self.grouping.ids(ctx)
        }

    def draw(self, image, ctx) -> None:
        """Drawn by s90_overlay under each person's hand label."""


def create_stage() -> AllScoresStage | None:
    """A debugging readout, on only for `python -m vision.watch --all-scores`."""
    import os

    return AllScoresStage() if os.environ.get("CUES_ALL_SCORES") == "1" else None
