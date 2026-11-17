"""Smoke test: one scripted lesson through vision's real people, hands and faces stages.

The pose, hand and gesture models are replaced by a script of landmarks (no camera), so every
other line is vision's own: the tracker that gives each child an id, the grouping that decides
whose hand is whose, and the face crop built from each child's head points. What the lesson
checks is what a teacher would notice go wrong in a real classroom:

    five children sit; one raises a hand next to a neighbour; a hand with no one behind it
    appears; a stray detection flashes for one frame; a child steps out and a stranger walks
    in on the far side.

The ids must stay with the same children, every hand must belong to the right child (or to no
one), nobody extra may be counted, and a still child's face crop must hold still.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from vision.camera import Frame
from vision.stages.s05_people import PeopleStage
from vision.stages.s10_hands import HandsStage
from vision.stages.s20_faces import FacesStage
from vision.station import ActiveStation

pytestmark = pytest.mark.smoke

FPS = 30
WIDTH, HEIGHT = 960, 540
SEATS = [0.10, 0.25, 0.40, 0.55, 0.70]  # five children, the right side of the room free


NOISE = np.random.default_rng(0)  # reset at the start of the lesson, so every run is the same


def pose(
    cx: float,
    *,
    raised: tuple[float, float] | None = None,
    guessed: tuple[float, float] | None = None,
    cy: float = 0.35,
) -> list:
    """A seated child's 33 pose points: head, shoulders and elbows seen, hips guessed.

    `guessed` puts the left wrist somewhere the model cannot actually see (low visibility).
    """
    s = 0.06
    points = np.zeros((33, 4), dtype=np.float32)
    points[:, 3] = 0.1  # hips and legs hidden, as at a desk
    seen = {
        0: (cx, cy),
        1: (cx - 0.01, cy - 0.015), 2: (cx - 0.015, cy - 0.015), 3: (cx - 0.02, cy - 0.015),
        4: (cx + 0.01, cy - 0.015), 5: (cx + 0.015, cy - 0.015), 6: (cx + 0.02, cy - 0.015),
        7: (cx - 0.03, cy), 8: (cx + 0.03, cy),
        9: (cx - 0.01, cy + 0.02), 10: (cx + 0.01, cy + 0.02),
        11: (cx + s, cy + 0.1), 12: (cx - s, cy + 0.1),
        13: (cx + s * 1.3, cy + 0.2), 14: (cx - s * 1.3, cy + 0.2),
        15: raised or (cx + s * 1.1, cy + 0.3), 16: (cx - s * 1.1, cy + 0.3),
    }  # fmt: skip
    for index, (x, y) in seen.items():
        points[index] = (x, y, 0.0, 0.9)
    if guessed is not None:
        points[15] = (*guessed, 0.0, 0.05)
    return [
        SimpleNamespace(x=float(x), y=float(y), z=0.0, visibility=float(v)) for x, y, _, v in points
    ]


def hand(x: float, y: float) -> list:
    return [SimpleNamespace(x=x, y=y, z=0.0) for _ in range(21)]


class Script:
    """Stands in for the pose model and the gesture recogniser: answers with what is scripted."""

    def __init__(self) -> None:
        self.poses: list[list] = []
        self.hands: list[list] = []

    def detect_for_video(self, image, timestamp_ms):
        """The scripted poses, with the head points shaking by about 3 pixels from frame to
        frame, as a real pose model's do."""
        shaken = []
        for person in self.poses:
            shake = NOISE.normal(0, 0.003, (11, 2))
            shaken.append(
                [
                    SimpleNamespace(x=p.x + dx, y=p.y + dy, z=p.z, visibility=p.visibility)
                    for p, (dx, dy) in zip(person[:11], shake, strict=True)
                ]
                + person[11:]
            )
        return SimpleNamespace(pose_landmarks=shaken)

    def recognize(self, image):
        return SimpleNamespace(
            hand_landmarks=self.hands,
            handedness=[[SimpleNamespace(category_name="Right")] for _ in self.hands],
            gestures=[[] for _ in self.hands],
        )


class Lesson:
    """The three real stages in vision's own order, fed frame by frame."""

    def __init__(self) -> None:
        station = ActiveStation("S1")
        self.script = Script()
        self.people = PeopleStage(detector=self.script, station=station)
        self.hands = HandsStage(detector=self.script, zones=self.people.grouping)
        self.faces = FacesStage()
        self.index = 0
        self.ctx: dict = {}

    def run(self, seconds: float) -> dict:
        for _ in range(round(seconds * FPS)):
            frame = Frame(
                image=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8),
                timestamp=self.index / FPS,
                index=self.index,
            )
            self.index += 1
            self.ctx = {}
            for stage in (self.people, self.hands, self.faces):
                stage.process(frame, self.ctx)
        return self.ctx

    def seat_of(self, ctx_person: str) -> float:
        box = self.ctx["people"][ctx_person].box
        return (box[0] + box[2]) / 2


def where(lesson: Lesson) -> dict[str, float]:
    """Each id's horizontal position now."""
    return {pid: lesson.seat_of(pid) for pid in lesson.ctx["people"]}


def test_a_lesson_keeps_every_child_their_own_id_hand_and_face():
    NOISE.bit_generator.state = np.random.default_rng(0).bit_generator.state
    lesson = Lesson()
    lesson.script.poses = [pose(x) for x in SEATS]
    ctx = lesson.run(2.0)

    # Five children sit: five ids, left to right, held for as long as they stay.
    seated = where(lesson)
    assert len(seated) == 5 and ctx["person_ids"] == sorted(seated)
    by_seat = sorted(seated, key=seated.get)

    # The third child raises a hand beside the fourth, whose own hand stays down. The fourth
    # child's other wrist is one the pose model cannot see: its guess lands right on the raised
    # hand. Two more hands appear: the fourth child's own, and one with no one behind it.
    raised = (SEATS[2] + 0.04, 0.3)
    guess = (SEATS[2] + 0.06, 0.3)
    lesson.script.poses = [
        pose(x, raised=raised if i == 2 else None, guessed=guess if i == 3 else None)
        for i, x in enumerate(SEATS)
    ]
    lesson.script.hands = [
        hand(*guess),  # the raised hand, as the hand model sees it
        hand(SEATS[3] - 0.066, 0.65),  # the fourth child's own hand, resting
        hand(0.18, 0.30),  # nobody's: no child is reaching there
    ]
    ctx = lesson.run(0.5)
    assert by_seat[2] in ctx["hands"], "the child with a hand up has no hand"
    assert len(ctx["hands"][by_seat[2]]) == 1, "the raised hand went to someone else"
    assert len(ctx["hands"].get(by_seat[3], [])) == 1
    assert set(ctx["hands"]) == {by_seat[2], by_seat[3]}, "a stray hand was given away"

    # One frame of a sixth, phantom detection beside the fifth child: nobody extra is counted.
    lesson.script.hands = []
    lesson.script.poses = [pose(x) for x in SEATS]
    lesson.run(0.5)
    lesson.script.poses = [pose(x) for x in SEATS] + [pose(SEATS[4] + 0.03, cy=0.5)]
    ctx = lesson.run(1 / FPS)
    assert len(ctx["people"]) == 5 and len(ctx["person_ids"]) == 5
    lesson.script.poses = [pose(x) for x in SEATS]
    lesson.run(0.5)
    assert len(lesson.ctx["person_ids"]) == 5

    # The first child steps out for a second; a stranger takes the far side of the room.
    lesson.script.poses = [pose(x) for x in SEATS[1:]]
    lesson.run(1.0)
    lesson.script.poses = [pose(x) for x in SEATS[1:]] + [pose(0.93)]
    ctx = lesson.run(0.8)
    now = where(lesson)
    assert len(now) == 5
    assert by_seat[0] in ctx["person_ids"], "the child who stepped out lost their id too soon"
    stranger = next(pid for pid in now if pid not in by_seat)
    assert stranger not in by_seat, "the stranger took over a child's id"
    for pid in by_seat[1:]:
        assert abs(now[pid] - seated[pid]) < 0.03, f"{pid} moved to another child"

    # Every person has a face of their own, over their own head, and a still child's crop holds.
    boxes = []
    for _ in range(30):
        ctx = lesson.run(1 / FPS)
        boxes.append(ctx["faces"][by_seat[2]].box)
    assert set(ctx["faces"]) == set(ctx["people"])
    for pid, face in ctx["faces"].items():
        centre = (face.box[0] + face.box[2]) / 2 / WIDTH
        assert abs(centre - where(lesson)[pid]) < 0.03, f"{pid}'s face is over someone else"
    assert float(np.std(np.array(boxes), axis=0).max()) < 1.5, "a still child's crop jumps about"
