"""Raise-hand rule: checks whether a child has raised a hand.

People mode (default): the score is a confidence from 0 to 1 computed from the
person's pose points (see raise_confidence). The status logic then requires
the score to stay above the activity's thresholds, which acts as the hold time.

Seats mode (the rest of this docstring):

The rule needs no recorded examples. A seat passes when a wrist in that seat is
above the top of the face in the same seat, and stays there for HOLD_SECONDS.
The hold time stops a quick wave from counting as a raised hand.

The stage runs only for seats whose current task is `raise_hand`. It writes
ctx["match"][seat_id] = Match("raise_hand", score) with score 1.0 (raised and
held) or 0.0 (not raised). If the seat has no visible face, the stage cannot
judge, so it writes score None with a reason.

Image coordinates grow downward, so "above" means a smaller y value.
"""

from __future__ import annotations

import cv2

from vision import activities
from vision.activities import TASKS
from vision.grouping import GROUPING
from vision.perception import Match
from vision.stages.s00_seats import seat_color

FLAG = "vision.raise_hand"
ACTIVITY_ID = "raise_hand"
HOLD_SECONDS = 0.5
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


def wrist_above_face(hands, face, image_height: int) -> bool:
    """True if any wrist in the seat is higher in the image than the face top."""
    face_top = face.box[1]
    return any(hand.wrist[1] * image_height < face_top for hand in hands)


class RaiseHandStage:
    name = "raise_hand"
    rate_hz = None  # every frame, so the hold time is measured accurately

    def __init__(self, tasks=TASKS, zones=GROUPING, hold_seconds: float = HOLD_SECONDS) -> None:
        self.tasks = tasks
        self.zones = zones
        self.hold_seconds = hold_seconds
        self._raised_since: dict[str, float] = {}

    def process(self, frame, ctx) -> None:
        image_height = frame.image.shape[0]
        hands = ctx.get("hands", {})
        faces = ctx.get("faces", {})
        matches = ctx.setdefault("match", {})
        people_mode = getattr(self.zones, "mode", "seats") == "people"
        for seat in self.zones.ids(ctx):
            if self.tasks.for_seat(seat) != ACTIVITY_ID:
                self._raised_since.pop(seat, None)
                if getattr(matches.get(seat), "activity_id", None) == ACTIVITY_ID:
                    del matches[seat]  # task changed: drop the old raise-hand result
                continue
            if people_mode:
                person = ctx.get("people", {}).get(seat)
                if person is None:
                    matches[seat] = Match(ACTIVITY_ID, None, "person not visible")
                else:
                    score, detail = raise_confidence(person)
                    matches[seat] = Match(ACTIVITY_ID, score, detail=detail)
                continue
            face = faces.get(seat)
            if face is None:
                self._raised_since.pop(seat, None)
                matches[seat] = Match(ACTIVITY_ID, None, "no face in this seat")
                continue
            raised = wrist_above_face(hands.get(seat, []), face, image_height)
            if not raised:
                self._raised_since.pop(seat, None)
                matches[seat] = Match(ACTIVITY_ID, 0.0, detail="hand not above face")
                continue
            since = self._raised_since.setdefault(seat, frame.timestamp)
            held = frame.timestamp - since
            score = 1.0 if held >= self.hold_seconds else 0.0
            matches[seat] = Match(ACTIVITY_ID, score, detail=f"hand above face for {held:.1f}s")

    def draw(self, image, ctx) -> None:
        for seat, face in ctx.get("faces", {}).items():
            match = ctx.get("match", {}).get(seat)
            if match is None or match.activity_id != ACTIVITY_ID:
                continue
            x0, y0, x1, _ = face.box
            # The line every wrist must rise above.
            cv2.line(image, (0, y0), (image.shape[1], y0), seat_color(seat), 1)
            if match.score == 1.0:
                cv2.putText(
                    image,
                    "HAND RAISED",
                    (x0, max(14, y0 - 24)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 200, 0),
                    2,
                )


def create_stage() -> RaiseHandStage:
    activities.get(ACTIVITY_ID)  # fail fast if the activity is missing from activities.json
    return RaiseHandStage()
