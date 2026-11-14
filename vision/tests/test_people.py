"""People mode: tracking ids, assigning hands and faces, pose-based raise-hand."""

import numpy as np
import pytest

from vision.activities import CurrentTasks
from vision.camera import Frame
from vision.people import (
    LEFT_SHOULDER,
    LEFT_WRIST,
    NOSE,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    PeopleGrouping,
    Person,
    PersonTracker,
    box_from_landmarks,
    grouping_from_env,
)
from vision.stages.s35_raise_hand import RaiseHandStage, raise_confidence


def pose(cx, cy=0.5, scale=0.1, wrist_up=False, vis=1.0):
    """A 33-point pose centred at (cx, cy). Shoulders 2*scale wide."""
    lm = np.zeros((33, 4), np.float32)
    lm[:, 0], lm[:, 1], lm[:, 3] = cx, cy, vis
    lm[NOSE, :2] = (cx, cy - 1.0 * scale)
    lm[LEFT_SHOULDER, :2] = (cx + scale, cy)
    lm[RIGHT_SHOULDER, :2] = (cx - scale, cy)
    lm[LEFT_WRIST, :2] = (cx + scale, cy + 2 * scale)
    lm[RIGHT_WRIST, :2] = (cx - scale, cy - 3.5 * scale if wrist_up else cy + 2 * scale)
    lm[23:25, :2] = [(cx + scale, cy + 3 * scale), (cx - scale, cy + 3 * scale)]  # hips
    return lm


def people_ctx(*poses, t=0.0, tracker=None):
    tracker = tracker or PersonTracker()
    people = tracker.update(t, list(poses))
    return {"people": people, "person_ids": tracker.live_ids}, tracker


# ---- tracker ---------------------------------------------------------------
def test_new_people_get_lowest_free_ids():
    tr = PersonTracker()
    people = tr.update(0.0, [pose(0.2), pose(0.7)])
    assert set(people) == {"S1-P1", "S1-P2"}


def test_ids_follow_people_who_move_a_little():
    tr = PersonTracker()
    first = tr.update(0.0, [pose(0.2), pose(0.7)])
    left_id = next(pid for pid, p in first.items() if p.box[0] < 0.5)
    again = tr.update(0.1, [pose(0.72), pose(0.23)])  # order swapped, small moves
    moved_left = next(pid for pid, p in again.items() if p.box[0] < 0.5)
    assert moved_left == left_id


def test_ids_are_released_after_the_timeout_and_reused():
    tr = PersonTracker(release_seconds=10)
    tr.update(0.0, [pose(0.2)])
    assert tr.update(5.0, []) == {}  # not visible
    assert tr.live_ids == ["S1-P1"]  # still live: status can report tracking_lost
    tr.update(11.0, [])
    assert tr.live_ids == []
    assert set(tr.update(12.0, [pose(0.8)])) == {"S1-P1"}


def test_at_most_four_people():
    tr = PersonTracker()
    people = tr.update(0.0, [pose(x) for x in (0.1, 0.3, 0.5, 0.7, 0.9)])
    assert len(people) == 4


def test_box_uses_upper_body_only():
    x0, y0, x1, y1 = box_from_landmarks(pose(0.5))
    assert x0 < 0.4 and x1 > 0.6 and y0 < 0.4
    assert y1 < 0.75  # hips at 0.8 are ignored


def test_unreliable_pose_is_skipped():
    assert box_from_landmarks(pose(0.5, vis=0.2)) is None


def test_box_is_smoothed_between_frames():
    tr = PersonTracker()
    first = tr.update(0.0, [pose(0.5)])["S1-P1"].box
    second = tr.update(0.1, [pose(0.55)])["S1-P1"].box
    raw = box_from_landmarks(pose(0.55))
    assert first[0] < second[0] < raw[0]  # moved, but only part of the way


def test_person_survives_a_short_miss_but_not_a_long_one():
    tr = PersonTracker()
    tr.update(0.0, [pose(0.5)])
    assert "S1-P1" in tr.update(0.3, [])  # missed one frame: still shown
    assert tr.update(1.0, []) == {}  # gone from view (still a live id)
    assert tr.live_ids == ["S1-P1"]
    assert set(tr.update(1.2, [pose(0.52)])) == {"S1-P1"}  # same id when back


# ---- grouping --------------------------------------------------------------
def test_hand_goes_to_the_person_with_the_nearest_wrist():
    ctx, _ = people_ctx(pose(0.2), pose(0.7))
    g = PeopleGrouping()
    hand = np.zeros((21, 3), np.float32)
    hand[0, :2] = (0.71, 0.70)  # near person 2's left wrist (0.8, 0.7)? no: (0.7+0.1, 0.7)
    right_person = next(pid for pid, p in ctx["people"].items() if p.box[0] > 0.5)
    assert g.hand_owner(hand, ctx) == right_person


def test_face_goes_to_the_person_whose_nose_is_inside_it():
    ctx, _ = people_ctx(pose(0.2), pose(0.7))
    g = PeopleGrouping()
    left_person = next(pid for pid, p in ctx["people"].items() if p.box[0] < 0.5)
    assert g.face_owner(0.2, 0.4, (0.15, 0.35, 0.25, 0.45), ctx) == left_person


def test_detections_outside_everyone_are_ignored():
    ctx, _ = people_ctx(pose(0.2))
    hand = np.zeros((21, 3), np.float32)
    hand[0, :2] = (0.95, 0.05)
    assert PeopleGrouping().hand_owner(hand, ctx) is None


def test_grouping_is_always_people(monkeypatch):
    monkeypatch.setenv("CUES_GROUPING", "seats")  # old setting: ignored
    assert grouping_from_env().mode == "people"


# ---- raise-hand confidence -------------------------------------------------
def test_raised_wrist_gives_high_confidence_and_lowered_gives_zero():
    up, _ = raise_confidence(Person("S1-P1", (0, 0, 1, 1), pose(0.5, wrist_up=True)))
    down, _ = raise_confidence(Person("S1-P1", (0, 0, 1, 1), pose(0.5)))
    assert up > 0.9
    assert down == 0.0


def test_low_visibility_lowers_confidence():
    clear, _ = raise_confidence(Person("S1-P1", (0, 0, 1, 1), pose(0.5, wrist_up=True)))
    faint, _ = raise_confidence(Person("S1-P1", (0, 0, 1, 1), pose(0.5, wrist_up=True, vis=0.4)))
    assert faint == pytest.approx(clear * 0.4, abs=0.01)


def test_confidence_does_not_depend_on_distance_from_camera():
    near, _ = raise_confidence(Person("a", (0, 0, 1, 1), pose(0.5, scale=0.15, wrist_up=True)))
    far, _ = raise_confidence(Person("a", (0, 0, 1, 1), pose(0.5, scale=0.05, wrist_up=True)))
    assert near == pytest.approx(far, abs=0.01)


def test_raise_stage_scores_each_person():
    ctx, _ = people_ctx(pose(0.2, wrist_up=True), pose(0.7))
    stage = RaiseHandStage(tasks=CurrentTasks("raise_hand"), zones=PeopleGrouping())
    stage.process(Frame(np.zeros((480, 640, 3), np.uint8), 0.0, 1), ctx)
    scores = {pid: ctx["match"][pid].score for pid in ctx["person_ids"]}
    left = next(pid for pid, p in ctx["people"].items() if p.box[0] < 0.5)
    right = next(pid for pid in scores if pid != left)
    assert scores[left] > 0.9 and scores[right] == 0.0


def test_status_stage_drops_released_people():
    from vision.stages.s50_status import StatusStage
    from vision.tests.test_status import RecordingEmitter

    stage = StatusStage(
        emitter=RecordingEmitter(), tasks=CurrentTasks("raise_hand"), zones=PeopleGrouping()
    )
    img = np.zeros((480, 640, 3), np.uint8)
    ctx, tracker = people_ctx(pose(0.3), t=0.0)
    stage.process(Frame(img, 0.0, 1), ctx)
    assert "S1-P1" in ctx["status"]
    tracker.update(20.0, [])  # released after 10 s out of view
    ctx = {"people": {}, "person_ids": tracker.live_ids}
    stage.process(Frame(img, 20.0, 2), ctx)
    assert ctx["status"] == {}


def test_person_label_is_two_short_lines():
    from vision.perception import Match
    from vision.stages.s05_people import person_label

    ctx = {
        "match": {"S1-P1": Match("raise_hand", 0.82)},
        "status": {"S1-P1": "done"},
        "last_event": {"S1-P1": "attempt_success"},
        "expression": {"S1-P1": {"neutral": 0.7, "happiness": 0.3}},
    }
    assert person_label("S1-P1", ctx) == [
        "P1  raise_hand 0.82",
        "done  attempt_success  neutral",
    ]
    assert person_label("S1-P2", {}) == ["P2"]


# ---- overlay ---------------------------------------------------------------
def overlay_ctx(with_face=True):
    from vision.perception import Face, Hand, Match
    from vision.tests.test_perception import hand_points

    ctx, _ = people_ctx(pose(0.3, wrist_up=True))
    hand = Hand(hand_points((0.35, 0.3), scale=0.08), "Right", "S1-P1")
    ctx["hands"] = {"S1-P1": [hand]}
    ctx["match"] = {"S1-P1": Match("raise_hand", 0.82, hand=hand)}
    ctx["expression"] = {"S1-P1": {"neutral": 0.61, "happiness": 0.3}}
    if with_face:
        ctx["faces"] = {
            "S1-P1": Face((150, 150, 230, 240), np.zeros((90, 80, 3), np.uint8), "S1-P1")
        }
    return ctx


def test_overlay_draws_face_and_hand_without_error():
    from vision.stages.s90_overlay import OverlayStage

    stage = OverlayStage(grouping=PeopleGrouping())
    for with_face in (True, False):
        ctx = overlay_ctx(with_face)
        stage.process(Frame(np.zeros((480, 640, 3), np.uint8), 1.0, 1), ctx)
        img = np.zeros((480, 640, 3), np.uint8)
        stage.draw(img, ctx)
        assert img.any()


def test_overlay_face_box_is_smoothed_and_kept_briefly():
    from vision.perception import Face
    from vision.stages.s90_overlay import OverlayStage

    stage = OverlayStage(grouping=PeopleGrouping())
    blank = np.zeros((480, 640, 3), np.uint8)
    face = lambda x: {"S1-P1": Face((x, 100, x + 80, 190), blank[:1, :1], "S1-P1")}  # noqa: E731
    ctx = {"faces": face(100)}
    stage.process(Frame(blank, 0.0, 1), ctx)
    ctx = {"faces": face(140)}
    stage.process(Frame(blank, 0.1, 2), ctx)
    assert 100 < ctx["overlay_faces"]["S1-P1"][0] < 140  # moved part of the way
    ctx = {"faces": {}}
    stage.process(Frame(blank, 0.4, 3), ctx)
    assert "S1-P1" in ctx["overlay_faces"]  # missed briefly: still shown
    stage.process(Frame(blank, 1.0, 4), ctx)
    assert "S1-P1" not in ctx["overlay_faces"]


def test_score_colour_follows_task_thresholds():
    from vision.stages.s90_overlay import GREEN, GREY, ORANGE, score_color

    assert score_color("raise_hand", 0.9) == GREEN
    assert score_color("raise_hand", 0.5) == ORANGE
    assert score_color("raise_hand", 0.1) == GREY
    assert score_color("raise_hand", None) == GREY
