"""Recognise mode: picks the gesture a person is doing, display only."""

import numpy as np
import pytest

from vision import mode
from vision.camera import Frame
from vision.gestures import templates as tpl
from vision.gestures.normalize import normalize
from vision.people import PeopleGrouping
from vision.perception import Hand, Match
from vision.stages.s30_gestures import MatcherCache
from vision.stages.s46_recognize import Recognizer, RecognizeStage, candidate
from vision.tests.test_people import people_ctx, pose
from vision.tests.test_perception import hand_points

IMG = np.zeros((4, 4, 3), np.uint8)


@pytest.fixture
def cache(tmp_path):
    rng = np.random.default_rng(3)
    target = normalize(hand_points(shape_seed=1))
    t = tpl.Templates("thumbs_up")
    t.add("target", [target + rng.normal(0, 0.003, 63) for _ in range(6)])
    tpl.save(t, tmp_path)
    return MatcherCache(tmp_path)


def ctx_with(raised: bool, thumb: bool):
    ctx, _ = people_ctx(pose(0.3, wrist_up=raised))
    shape = 1 if thumb else 2
    ctx["hands"] = {"S1-P1": [Hand(hand_points((0.3, 0.6), shape_seed=shape), "Right", "S1-P1")]}
    return ctx


def run(stage, ctx_fn, start, seconds, step=0.1):
    ctx = None
    for i in range(int(round(seconds / step)) + 1):
        ctx = ctx_fn()
        stage.process(Frame(IMG, start + i * step, i), ctx)
    return ctx


def stage(cache):
    return RecognizeStage(grouping=PeopleGrouping(), cache=cache, enabled=True)


def test_mode_setting(monkeypatch):
    monkeypatch.delenv("CUES_MODE", raising=False)
    assert mode.current() == "task" and not mode.recognizing()
    monkeypatch.setenv("CUES_MODE", "recognize")
    assert mode.recognizing()
    monkeypatch.setenv("CUES_MODE", "freestyle")
    with pytest.raises(ValueError):
        mode.current()


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
    ctx = run(stage(cache), lambda: ctx_with(raised=False, thumb=False), 0.0, 1.0)
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


def test_off_in_task_mode(cache):
    st = RecognizeStage(grouping=PeopleGrouping(), cache=cache, enabled=False)
    ctx = ctx_with(raised=True, thumb=True)
    st.process(Frame(IMG, 0.0, 1), ctx)
    assert "recognized" not in ctx


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
