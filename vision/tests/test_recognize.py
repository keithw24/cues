"""Recognise mode: picks the gesture a person is doing, display only."""

import numpy as np
import pytest

from vision.camera import Frame
from vision.gestures import templates as tpl
from vision.gestures.normalize import normalize
from vision.people import PeopleGrouping
from vision.perception import Hand, Match
from vision.stages.s30_gestures import MatcherCache
from vision.stages.s46_recognize import Recognizer, RecognizeStage, candidate
from vision.tests.hands import PERSONS_RIGHT, open_palm, thumbs_up_back
from vision.tests.test_people import people_ctx, pose

IMG = np.zeros((4, 4, 3), np.uint8)


@pytest.fixture
def cache(tmp_path):
    rng = np.random.default_rng(3)
    target = normalize(thumbs_up_back(), PERSONS_RIGHT)
    t = tpl.Templates("thumbs_up")
    t.add("target", [target + rng.normal(0, 0.003, 63) for _ in range(6)])
    tpl.save(t, tmp_path)
    return MatcherCache(tmp_path)


def ctx_with(raised: bool, thumb: bool):
    """A person with their hand raised or not, showing a thumbs-up or an open palm."""
    ctx, _ = people_ctx(pose(0.3, wrist_up=raised))
    pts = (
        thumbs_up_back(cy=0.15 if raised else 0.6)
        if thumb
        else open_palm(cy=0.25 if raised else 0.6)
    )
    thumb_scores = {"Thumb_Up": 0.92, "Open_Palm": 0.01}
    palm_scores = {"Thumb_Up": 0.0, "Open_Palm": 0.95}
    scores = thumb_scores if thumb else palm_scores
    ctx["hands"] = {"S1-P1": [Hand(pts, PERSONS_RIGHT, "S1-P1", scores)]}
    return ctx


def run(stage, ctx_fn, start, seconds, step=0.1):
    ctx = None
    for i in range(int(round(seconds / step)) + 1):
        ctx = ctx_fn()
        stage.process(Frame(IMG, start + i * step, i), ctx)
    return ctx


def stage(cache):
    return RecognizeStage(
        grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up", "raise_hand")
    )


def test_candidate_needs_the_gestures_own_success_threshold():
    assert candidate({"raise_hand": (0.65, None), "thumbs_up": (0.5, None)}) == (None, None)
    assert candidate({"raise_hand": (0.75, None), "thumbs_up": (0.9, None)}) == ("thumbs_up", 0.9)
    assert candidate({"raise_hand": (None, None), "thumbs_up": (None, None)}) == (None, None)


def test_recognizes_thumbs_up_then_switches_to_raise_hand(cache):
    st = stage(cache)
    ctx = run(st, lambda: ctx_with(raised=False, thumb=True), 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == "thumbs_up"
    ctx = run(st, lambda: ctx_with(raised=True, thumb=False), 1.1, 1.0)
    rec = ctx["recognized"]["S1-P1"]
    assert rec.activity_id == "raise_hand" and rec.score > 0.7


def test_nothing_recognized_for_a_resting_hand(cache):
    ctx = run(stage(cache), lambda: ctx_with(raised=False, thumb=False), 0.0, 1.0)  # palm, low
    rec = ctx["recognized"]["S1-P1"]
    assert rec.activity_id is None and rec.hand is not None  # hand still shown


def test_hysteresis_ignores_brief_changes():
    r = Recognizer(switch_seconds=0.5)
    for i in range(8):
        r.update(i * 0.1, "thumbs_up")
    assert r.shown == "thumbs_up"
    r.update(0.8, "raise_hand")
    r.update(0.9, "raise_hand")  # 0.1 s: too short
    assert r.update(1.0, "thumbs_up") == "thumbs_up"
    for i in range(7):
        r.update(1.1 + i * 0.1, "raise_hand")  # 0.6 s: long enough
    assert r.shown == "raise_hand"


def test_recognize_mode_is_display_only(cache):
    ctx = ctx_with(raised=True, thumb=False)
    assigned = Match("thumbs_up", 0.1)
    ctx["match"] = {"S1-P1": assigned}
    stage(cache).process(Frame(IMG, 0.0, 1), ctx)
    assert ctx["match"] == {"S1-P1": assigned}  # assigned task untouched
    assert "status" not in ctx


def test_overlay_and_watch_show_the_recognized_gesture(cache):
    from vision.stages.s46_recognize import Recognized
    from vision.stages.s90_overlay import OverlayStage
    from vision.watch import format_seat

    ctx = ctx_with(raised=True, thumb=False)
    hand = ctx["hands"]["S1-P1"][0]
    ctx["recognized"] = {"S1-P1": Recognized("raise_hand", 0.88, hand)}
    ov = OverlayStage(grouping=PeopleGrouping())
    ov.process(Frame(IMG, 0.0, 1), ctx)
    img = np.zeros((480, 640, 3), np.uint8)
    ov.draw(img, ctx)
    assert img.any()
    text = format_seat("S1-P1", "thumbs_up", None, None, recognized=ctx["recognized"]["S1-P1"])
    assert "Recognised: raise_hand 0.88" in text
    none = format_seat("S1-P1", "thumbs_up", None, None, recognized=Recognized(None, None, None))
    assert "Recognised: no gesture" in none


# ---- hand-shape rules ------------------------------------------------------
def test_raised_thumbs_up_is_not_a_raised_hand(cache):
    ctx = run(stage(cache), lambda: ctx_with(raised=True, thumb=True), 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == "thumbs_up"


def test_raised_open_palm_is_a_raised_hand_not_a_thumbs_up(cache):
    ctx = run(stage(cache), lambda: ctx_with(raised=True, thumb=False), 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == "raise_hand"


def test_scores_respect_hand_side(cache):
    from vision.stages.s46_recognize import score_gestures

    scores = score_gestures(
        "S1-P1", ctx_with(raised=True, thumb=True), cache, ("thumbs_up", "raise_hand")
    )
    assert scores["raise_hand"][0] == 0.0  # raised, but not an open palm
    assert scores["thumbs_up"][0] == pytest.approx(0.92)
    scores = score_gestures(
        "S1-P1", ctx_with(raised=True, thumb=False), cache, ("thumbs_up", "raise_hand")
    )
    assert scores["thumbs_up"][0] == 0.0  # palm facing the camera: not a thumbs-up
    assert scores["raise_hand"][0] > 0.7


def test_hand_side_always_shown_in_recognise_mode():
    from vision.stages.s46_recognize import Recognized
    from vision.tests.hands import PERSONS_RIGHT, open_palm
    from vision.watch import format_seat

    hand = Hand(open_palm(), PERSONS_RIGHT, "S1-P1")
    text = format_seat("S1-P1", "thumbs_up", None, None, recognized=Recognized(None, None, hand))
    assert "Hand: palm, open (4/4 fingers)" in text  # without --debug
    none = format_seat("S1-P1", "thumbs_up", None, None, recognized=Recognized(None, None, None))
    assert "Hand: none detected" in none


def test_raised_palm_that_the_recogniser_does_not_call_open_is_not_a_raised_hand(cache):
    from vision.stages.s46_recognize import score_gestures

    ctx = ctx_with(raised=True, thumb=False)
    ctx["hands"]["S1-P1"][0].gestures = {"Open_Palm": 0.2, "Closed_Fist": 0.7}
    scores = score_gestures("S1-P1", ctx, cache, ("thumbs_up", "raise_hand"))
    assert scores["raise_hand"][0] == 0.0


# ---- always-on detection ---------------------------------------------------
def test_detects_every_known_activity(monkeypatch):
    from vision.stages.s46_recognize import all_gesture_ids

    monkeypatch.setenv("CUES_FLAG_VISION_RAISE_HAND", "1")
    assert set(all_gesture_ids()) == {
        "thumbs_up", "raise_hand", "custom_gesture_01", "open_palm", "pointing", "peace", "fist",
    }  # fmt: skip
    monkeypatch.setenv("CUES_FLAG_VISION_RAISE_HAND", "0")
    assert "raise_hand" not in all_gesture_ids()


def test_raise_hand_task_needs_an_open_palm_facing_the_camera():
    from vision.activities import CurrentTasks
    from vision.stages.s35_raise_hand import RaiseHandStage

    stage = RaiseHandStage(tasks=CurrentTasks("raise_hand"), zones=PeopleGrouping())
    palm = ctx_with(raised=True, thumb=False)
    stage.process(Frame(IMG, 0.0, 1), palm)
    assert palm["match"]["S1-P1"].score > 0.7  # raised open palm: counts
    thumb = ctx_with(raised=True, thumb=True)
    stage.process(Frame(IMG, 0.1, 2), thumb)
    assert thumb["match"]["S1-P1"].score == 0.0  # raised thumbs-up: does not
    assert "palm not open" in thumb["match"]["S1-P1"].detail


def test_overlay_falls_back_to_the_assigned_task_when_no_gesture(cache):
    from vision.stages.s46_recognize import Recognized
    from vision.stages.s90_overlay import OverlayStage

    ctx = ctx_with(raised=False, thumb=False)
    hand = ctx["hands"]["S1-P1"][0]
    ctx["recognized"] = {"S1-P1": Recognized(None, None, hand)}
    ctx["match"] = {"S1-P1": Match("raise_hand", 0.2, hand=hand)}
    ov = OverlayStage(grouping=PeopleGrouping())
    ov.process(Frame(IMG, 0.0, 1), ctx)
    img = np.zeros((540, 960, 3), np.uint8)
    ov.draw(img, ctx)
    assert img.any()


# ---- open palm ---------------------------------------------------------------
def test_open_palm_is_built_in():
    from vision import activities

    act = activities.get("open_palm")
    assert act.builtin == "Open_Palm" and act.check_type == "gesture"


def test_open_palm_at_chest_height_is_open_palm(cache):
    st = RecognizeStage(
        grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up", "raise_hand", "open_palm")
    )
    ctx = run(st, lambda: ctx_with(raised=False, thumb=False), 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == "open_palm"


def test_raised_open_palm_is_raise_hand_not_open_palm(cache):
    st = RecognizeStage(
        grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up", "raise_hand", "open_palm")
    )
    ctx = run(st, lambda: ctx_with(raised=True, thumb=False), 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == "raise_hand"


def test_candidate_prefers_raise_hand_over_open_palm():
    from vision.stages.s46_recognize import candidate

    scores = {"open_palm": (0.95, None), "raise_hand": (0.8, None)}
    assert candidate(scores) == ("raise_hand", 0.8)
    assert candidate({"open_palm": (0.95, None), "raise_hand": (0.1, None)}) == ("open_palm", 0.95)


@pytest.mark.parametrize(
    "label,expected",
    [("Pointing_Up", "pointing"), ("Victory", "peace"), ("Closed_Fist", "fist")],
)
def test_new_built_in_gestures_are_recognized(cache, label, expected):
    from vision import activities

    assert activities.get(expected).builtin == label
    ids = ("thumbs_up", "raise_hand", "open_palm", "pointing", "peace", "fist")
    st = RecognizeStage(grouping=PeopleGrouping(), cache=cache, gesture_ids=ids)

    def ctx_fn():
        ctx = ctx_with(raised=False, thumb=True)
        ctx["hands"]["S1-P1"][0].gestures = {label: 0.9, "Thumb_Up": 0.05}
        return ctx

    ctx = run(st, ctx_fn, 0.0, 1.0)
    assert ctx["recognized"]["S1-P1"].activity_id == expected


def test_green_label_keeps_its_completed_score_through_a_hand_dropout(cache):
    from types import SimpleNamespace

    st = RecognizeStage(grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up",))
    ctx = ctx_with(raised=False, thumb=True)
    hand = ctx["hands"]["S1-P1"][0]
    hand.gestures = {"Thumb_Up": 0.9}
    for t in (0.0, 0.3, 0.6, 0.9):  # held long enough to show
        st.process(SimpleNamespace(timestamp=t), ctx)
    assert ctx["recognized"]["S1-P1"].activity_id == "thumbs_up"
    shown = ctx["recognized"]["S1-P1"]
    ctx["hands"]["S1-P1"] = []  # the hand is lost for 0.8 s
    for t in (1.0, 1.4, 1.7):
        st.process(SimpleNamespace(timestamp=t), ctx)
    kept = ctx["recognized"]["S1-P1"]
    assert kept.activity_id == "thumbs_up"
    assert shown.score == 0.9
    assert kept.score is None  # no hand in view: no score is made up for it
    assert kept.hand is None  # and no stale skeleton is drawn for a hand that is gone


def test_held_label_follows_the_live_hand_not_the_old_one(cache):
    from types import SimpleNamespace

    st = RecognizeStage(grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up",))
    ctx = ctx_with(raised=False, thumb=True)
    first = ctx["hands"]["S1-P1"][0]
    first.gestures = {"Thumb_Up": 0.9}
    for t in (0.0, 0.3, 0.6, 0.9):
        st.process(SimpleNamespace(timestamp=t), ctx)
    moved = ctx_with(raised=False, thumb=False)["hands"]["S1-P1"][0]  # a different pose
    moved.gestures = {"Thumb_Up": 0.05}
    ctx["hands"]["S1-P1"] = [moved]  # the hand is now doing something else
    st.process(SimpleNamespace(timestamp=1.1), ctx)
    held = ctx["recognized"]["S1-P1"]
    assert held.activity_id == "thumbs_up"
    assert held.score == pytest.approx(0.05)  # the live score, not the frozen 0.9
    assert held.hand is moved  # the skeleton follows the real hand


def test_held_gesture_score_falls_with_the_hand_instead_of_freezing(cache):
    from types import SimpleNamespace

    st = RecognizeStage(grouping=PeopleGrouping(), cache=cache, gesture_ids=("thumbs_up",))
    ctx = ctx_with(raised=False, thumb=True)
    hand = ctx["hands"]["S1-P1"][0]
    for t in (0.0, 0.3, 0.6, 0.9):
        hand.gestures = {"Thumb_Up": 0.9}
        st.process(SimpleNamespace(timestamp=t), ctx)
    seen = []
    for i, live in enumerate((0.8, 0.6, 0.45, 0.3, 0.1)):  # the gesture fades over 0.5 s
        hand.gestures = {"Thumb_Up": live}
        st.process(SimpleNamespace(timestamp=1.0 + i * 0.1), ctx)
        r = ctx["recognized"]["S1-P1"]
        assert r.activity_id == "thumbs_up"  # still held (inside 1.5 s)
        seen.append(r.score)
    assert seen == pytest.approx([0.8, 0.6, 0.45, 0.3, 0.1])  # every step visible, no plateau


# ---- only the selected task is checked; other gestures are shown in grey -----------------
GREEN_BGR = (0, 190, 0)  # the overlay's "completed" colour
GREY_BGR = (150, 150, 150)


def _paint(task, recognized_id, score):
    """Draw one person's overlay when `task` is selected and `recognized_id` is seen."""
    from vision.perception import Match
    from vision.stages.s46_recognize import Recognized
    from vision.stages.s90_overlay import OverlayStage

    ctx = ctx_with(raised=False, thumb=True)
    hand = ctx["hands"]["S1-P1"][0]
    ctx["match"] = {"S1-P1": Match(task, 0.2, hand=hand)}  # the selected task, barely started
    ctx["recognized"] = {"S1-P1": Recognized(recognized_id, score, hand)}
    ov = OverlayStage(grouping=PeopleGrouping())
    ov.process(Frame(IMG, 0.0, 1), ctx)
    img = np.zeros((480, 640, 3), np.uint8)
    ov.draw(img, ctx)
    return img


def _has(img, bgr):
    return bool((img == np.array(bgr, dtype=np.uint8)).all(axis=2).any())


def test_a_confident_gesture_that_is_not_the_selected_task_is_never_green():
    img = _paint("raise_hand", "thumbs_up", 0.97)  # a very confident thumbs up, but not the task
    assert not _has(img, GREEN_BGR)
    assert _has(img, GREY_BGR)  # still shown, in grey


def test_the_selected_task_turns_green_when_it_is_completed():
    img = _paint("thumbs_up", "thumbs_up", 0.9)
    assert _has(img, GREEN_BGR)


def test_a_non_task_gesture_adds_a_grey_note_and_keeps_the_tasks_own_label(monkeypatch):
    import vision.stages.s90_overlay as module

    labels = []
    monkeypatch.setattr(
        module, "label", lambda image, text, x, y, fill: labels.append((text, fill))
    )
    _paint("raise_hand", "thumbs_up", 0.97)
    assert any("raise_hand 0.20" in text for text, _ in labels)  # the selected task's own score
    note = [(text, fill) for text, fill in labels if "also seeing: thumbs_up 0.97" in text]
    assert note and note[0][1] == GREY_BGR
