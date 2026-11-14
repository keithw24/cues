"""Raise-hand rule: a 0-1 confidence that each person has raised a hand.

The score comes from the person's pose points (see raise_confidence). The
status logic then requires the score to stay above the activity's thresholds,
which acts as the hold time. The person's single displayed hand is their
highest MediaPipe hand (image y grows downward, so the smallest wrist y).
"""

from __future__ import annotations

from vision import activities
from vision.activities import TASKS
from vision.grouping import GROUPING
from vision.perception import Match
from vision.session_sync import frame_activity

FLAG = "vision.raise_hand"
ACTIVITY_ID = "raise_hand"
FULL_RAISE_SHOULDER_WIDTHS = 1.5


def raise_confidence(person) -> tuple[float, str]:
    """People mode: how clearly a person's hand is raised, from 0 to 1.

    Uses the person's MediaPipe pose points:
    * height: how far the higher wrist is above the shoulder line, measured in
      shoulder widths so it works near and far. Level with the shoulders gives
      0; FULL_RAISE_SHOULDER_WIDTHS above (about the top of the head) gives 1.
    * visibility: MediaPipe's own confidence that the wrist and shoulders are
      visible. A barely visible wrist lowers the score.
    confidence = height x visibility. Returns (confidence, explanation).
    """
    from vision.people import LEFT_SHOULDER, LEFT_WRIST, RIGHT_SHOULDER, RIGHT_WRIST

    _, lsy, lsv = person.point(LEFT_SHOULDER)
    _, rsy, rsv = person.point(RIGHT_SHOULDER)
    shoulder_y = (lsy + rsy) / 2
    width = max(person.shoulder_width, 1e-3)
    best, detail = 0.0, "no wrist above the shoulders"
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        _, wy, wv = person.point(wrist)
        height = (shoulder_y - wy) / width  # image y grows downward
        geometry = min(max(height / FULL_RAISE_SHOULDER_WIDTHS, 0.0), 1.0)
        visibility = min(wv, lsv, rsv)
        confidence = round(geometry * visibility, 3)
        if confidence > best:
            best = confidence
            detail = (
                f"wrist {height:.1f} shoulder widths above shoulders, visibility {visibility:.2f}"
            )
    return best, detail


def highest_hand(hands):
    """The hand whose wrist is highest in the image, or None."""
    return min(hands, key=lambda h: h.wrist[1]) if hands else None


class RaiseHandStage:
    name = "raise_hand"
    rate_hz = None  # every frame, so the hold time is measured accurately

    def __init__(self, tasks=TASKS, zones=GROUPING) -> None:
        self.tasks = tasks
        self.zones = zones

    def process(self, frame, ctx) -> None:
        hands = ctx.get("hands", {})
        matches = ctx.setdefault("match", {})
        for pid in self.zones.ids(ctx):
            if frame_activity(self.tasks, pid, ctx) != ACTIVITY_ID:
                if getattr(matches.get(pid), "activity_id", None) == ACTIVITY_ID:
                    del matches[pid]  # task changed: drop the old raise-hand result
                continue
            person = ctx.get("people", {}).get(pid)
            if person is None:
                matches[pid] = Match(ACTIVITY_ID, None, "person not visible")
                continue
            score, detail = raise_confidence(person)
            hand = highest_hand(hands.get(pid, []))
            matches[pid] = Match(ACTIVITY_ID, score, detail=detail, hand=hand)

    def draw(self, image, ctx) -> None:
        """Drawn by s90_overlay."""


def create_stage() -> RaiseHandStage:
    activities.get(ACTIVITY_ID)  # fail fast if the activity is missing from activities.json
    return RaiseHandStage()
