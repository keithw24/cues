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
    tr.update(5.0, [])
    assert tr.live_ids == ["S1-P1"]  # still live: status can report tracking_lost
    tr.update(11.0, [])
    assert tr.live_ids == []
    assert set(tr.update(12.0, [pose(0.8)])) == {"S1-P1"}


def test_at_most_four_people():
    tr = PersonTracker()
    people = tr.update(0.0, [pose(x) for x in (0.1, 0.3, 0.5, 0.7, 0.9)])
    assert len(people) == 4


def test_box_covers_visible_points():
    x0, y0, x1, y1 = box_from_landmarks(pose(0.5))
    assert x0 < 0.4 and x1 > 0.6 and y0 < 0.4 and y1 > 0.8


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


def test_grouping_mode_from_env(monkeypatch):
    monkeypatch.setenv("CUES_GROUPING", "seats")
    assert grouping_from_env().mode == "seats"
    monkeypatch.setenv("CUES_GROUPING", "people")
    assert grouping_from_env().mode == "people"
    monkeypatch.setenv("CUES_GROUPING", "rows")
    with pytest.raises(ValueError):
        grouping_from_env()


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
