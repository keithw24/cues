"""Gesture matching: a match score per seat for that seat's current gesture task.

Reads ctx["hands"] and writes ctx["match"] = {seat_id: Match}. Examples are
re-read when their file changes, so a gesture recorded while the service runs
is used within a second.
"""

from __future__ import annotations

import cv2

from vision import activities
from vision.activities import TASKS
from vision.gestures import templates as tpl
from vision.gestures.matcher import Matcher
from vision.gestures.normalize import normalize
from vision.grouping import GROUPING
from vision.people import person_color as seat_color
from vision.perception import Match
from vision.session_sync import frame_activity

FLAG = "vision.gestures"


class MatcherCache:
    """Loads a Matcher per activity and reloads it when its template file changes."""

    def __init__(self, directory=None) -> None:
        self.directory = directory
        self._cache: dict[str, tuple[float, Matcher | None, str]] = {}

    def get(self, activity_id: str) -> tuple[Matcher | None, str]:
        path = tpl.path_for(activity_id, self.directory)
        mtime = path.stat().st_mtime if path.exists() else -1.0
        cached = self._cache.get(activity_id)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
        try:
            matcher, reason = Matcher.from_templates(tpl.load(activity_id, self.directory)), ""
        except ValueError:
            matcher = None
            reason = f"no examples recorded (python -m vision.record {activity_id} target)"
        self._cache[activity_id] = (mtime, matcher, reason)
        return matcher, reason


class GesturesStage:
    name = "gestures"
    rate_hz = None

    def __init__(self, tasks=TASKS, zones=GROUPING, cache: MatcherCache | None = None) -> None:
        self.tasks = tasks
        self.zones = zones
        self.cache = cache or MatcherCache()

    def process(self, frame, ctx) -> None:
        hands = ctx.get("hands", {})
        result: dict[str, Match] = {}
        for seat in self.zones.ids(ctx):
            activity_id = frame_activity(self.tasks, seat, ctx)
            if activity_id is None:
                continue
            if activities.get(activity_id).check_type != "gesture":
                continue
            if seat not in hands:
                continue
            matcher, reason = self.cache.get(activity_id)
            if matcher is None:
                result[seat] = Match(activity_id, None, reason)
                continue
            scored = [
                (matcher.score(v), v, h)
                for h in hands[seat]
                for v in [normalize(h.landmarks, h.handedness)]
            ]
            score, best, hand = max(scored, key=lambda item: item[0])  # one hand per person
            d_target, d_rest = matcher.distances(best)
            detail = (
                f"nearest target {d_target:.2f}, nearest rest {d_rest:.2f}, "
                f"score reaches 0 at {matcher.rejection_threshold:.2f}"
            )
            result[seat] = Match(activity_id, score, detail=detail, hand=hand)
        ctx["match"] = result

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if not overlay.debug():
            return
        h, w = image.shape[:2]
        for seat, match in ctx.get("match", {}).items():
            anchor = self.zones.anchor(seat, ctx, w, h, row=2)
            if anchor is None:
                continue
            score = "--" if match.score is None else f"{match.score:.2f}"
            text = f"{match.activity_id}: {score}"
            cv2.putText(image, text, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.6, seat_color(seat), 2)


def create_stage() -> GesturesStage:
    return GesturesStage()
