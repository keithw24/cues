"""Drive vision's real status stage without a camera.

A camera frame is turned into who is in view, who has a hand up and each person's score for
the task (the pose, hand and gesture stages). Everything after that is vision's own code: the
status stage, the trackers that decide done / review / needs help / tracking lost, and the
shared event and seat-state contracts. This module stands in for the camera side only, so a
test can say "this child holds a low score for ten seconds" and see exactly what vision
would publish. No frame, image or landmark is involved at any point.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

SAD = {"sadness": 0.8, "neutral": 0.2}  # a model probability, never a state of the child


@dataclass(frozen=True)
class View:
    """What the camera side reports for one person in one frame."""

    in_view: bool = True  # the person's pose is tracked
    hand: bool = True  # a hand is up
    score: float | None = None  # match score for the current task, when a hand is up
    expression: dict[str, float] | None = None  # smoothed expression distribution


def apply_views(ctx: dict, views: dict[str, View], activity_id: str) -> dict:
    """Write one frame's perception results into the pipeline context, as the stages would."""
    from vision.perception import Match

    ctx["person_ids"] = list(views)
    ctx["people"] = {seat: object() for seat, v in views.items() if v.in_view}
    ctx["hands"] = {seat: [object()] for seat, v in views.items() if v.hand}
    ctx["faces"] = {}
    ctx["match"] = {
        seat: Match(activity_id, v.score)
        for seat, v in views.items()
        if v.hand and v.score is not None
    }
    ctx["expression"] = {seat: v.expression for seat, v in views.items() if v.expression}
    ctx["scorable"] = {activity_id: True}
    return ctx


class CapturingEmitter:
    """Stands in for vision.events.Emitter: keeps what vision would have written."""

    def __init__(self, station_id: str = "S1") -> None:
        self.station_id = station_id
        self.session_id = uuid.uuid4()
        self.events: list = []
        self.states: list = []

    def emit(self, event) -> None:
        self.events.append(event)

    def update_seat_state(self, state) -> None:
        self.states.append(state)

    def send_soon(self) -> None:
        pass

    def close(self) -> None:
        pass


def status_stage(emitter, station_id: str, activity_id: str = "thumbs_up", station=None):
    """The real status stage, wired to private copies of vision's shared state."""
    from vision.activities import CurrentTasks
    from vision.people import PeopleGrouping
    from vision.review_marks import ReviewMarks
    from vision.stages.s50_status import StatusStage
    from vision.station import ActiveStation

    return StatusStage(
        emitter=emitter,
        tasks=CurrentTasks(activity_id),
        zones=PeopleGrouping(station_id),
        station=station or ActiveStation(station_id),
        marks=ReviewMarks(),
    )


class ScriptedVision:
    """The real status stage over simulated frames, with `views` held until they are changed.

    Time is simulated (a minute of frames costs milliseconds) and starts in the past, so every
    row is dated as if it had just been observed. With `managed` the frames belong to a
    teacher's session, as in the real service; without it vision is offline and writes through
    whatever `emitter` it is given.
    """

    def __init__(
        self,
        views: dict[str, View],
        *,
        station_id: str = "S1",
        activity_id: str = "thumbs_up",
        managed: bool = True,
        emitter=None,
    ) -> None:
        from shared.contracts import Session

        self.views = dict(views)
        self.activity_id = activity_id
        self.emitter = emitter or CapturingEmitter(station_id)
        self.stage = status_stage(self.emitter, station_id, activity_id)
        self.session = Session(
            id=uuid.uuid4(),
            station_id=station_id,
            current_activity_id=activity_id,
            started_at=datetime.now(UTC),
            ended_at=None,
            revision=0,
        )
        self.ctx: dict = {"session_managed": True, "session": self.session} if managed else {}
        self.now = time.monotonic() - 600.0
        self.frames = 0
        self.marks: dict[str, datetime] = {}

    def run(self, seconds: float, step: float = 0.1) -> ScriptedVision:
        from vision.camera import Frame

        for _ in range(round(seconds / step)):
            apply_views(self.ctx, self.views, self.activity_id)
            self.frames += 1
            self.stage.process(Frame(image=None, timestamp=self.now, index=self.frames), self.ctx)
            self.now += step
        return self

    def mark_reviewed(self, seat: str) -> None:
        """The teacher's "Mark as reviewed", as the station tick hands it to vision."""
        self.marks[seat] = datetime.now(UTC)
        self.stage.marks.replace(str(self.session.id), dict(self.marks))


def scripted_run(views: dict[str, View], *, seconds: float = 60.0, **options):
    """Run `seconds` of frames with constant `views`. Returns (emitter, session)."""
    run = ScriptedVision(views, **options).run(seconds)
    return run.emitter, run.session


# One of everything vision can say: a child who finishes, one in the review band, one who
# stalls while a model reports a sustained negative expression, one who leaves the view.
def whole_class(station_id: str = "S1") -> dict[str, View]:
    return {
        f"{station_id}-P1": View(score=0.9),  # success held for a second: done
        f"{station_id}-P2": View(score=0.6),  # in the review band: review
        f"{station_id}-P3": View(score=0.1, expression=SAD),  # low score: needs help
        f"{station_id}-P4": View(in_view=False, hand=False),  # nobody in view: tracking lost
    }
