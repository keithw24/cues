"""Palm side and open-hand checks."""

import numpy as np

from vision.gestures.hand_pose import extended_fingers, is_open, palm_side
from vision.tests.hands import PERSONS_RIGHT, open_palm, thumbs_up_back


def rotate(pts, degrees):
    a = np.radians(degrees)
    out = pts.copy()
    c = out[0, :2].copy()
    xy = out[:, :2] - c
    out[:, :2] = xy @ np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]]) + c
    return out


def mirror(pts):
    out = pts.copy()
    out[:, 0] = 2 * out[0, 0] - out[:, 0]
    return out


def test_open_palm_faces_the_camera():
    assert palm_side(open_palm(), PERSONS_RIGHT) == "palm"
    assert is_open(open_palm()) and extended_fingers(open_palm()) == 4


def test_thumbs_up_shows_the_back_and_is_closed():
    assert palm_side(thumbs_up_back(), PERSONS_RIGHT) == "back"
    assert not is_open(thumbs_up_back())


def test_side_does_not_change_when_the_hand_tilts():
    for deg in (-40, -15, 15, 40):
        assert palm_side(rotate(open_palm(), deg), PERSONS_RIGHT) == "palm"
        assert palm_side(rotate(thumbs_up_back(), deg), PERSONS_RIGHT) == "back"


def test_left_hand_is_handled():
    # The person's left hand palm-out looks like a mirrored right hand; MediaPipe says "Right".
    assert palm_side(mirror(open_palm()), "Right") == "palm"


def test_flip_setting_swaps_palm_and_back(monkeypatch):
    monkeypatch.setenv("CUES_PALM_FLIP", "1")
    assert palm_side(open_palm(), PERSONS_RIGHT) == "back"


def test_edge_on_hand_is_side():
    pts = open_palm()
    pts[17, :2] = pts[5, :2] + (pts[5, :2] - pts[0, :2]) * 0.01  # knuckles in line
    assert palm_side(pts, PERSONS_RIGHT) == "side"


def test_old_templates_are_marked_stale(tmp_path):
    import json

    from vision.gestures import templates as tpl
    from vision.stages.s30_gestures import MatcherCache

    (tmp_path / "thumbs_up.json").write_text(json.dumps({"target": [[0.0] * 63], "rest": []}))
    assert tpl.load("thumbs_up", tmp_path).stale
    matcher, reason = MatcherCache(tmp_path).get("thumbs_up")
    assert matcher is None and "out of date" in reason
    t = tpl.Templates("thumbs_up")
    t.add("target", [np.ones(63)])
    tpl.save(t, tmp_path)
    assert not tpl.load("thumbs_up", tmp_path).stale
