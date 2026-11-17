"""The normal video overlay: one face box and one hand per person.

For each tracked person this stage draws, in that person's colour:

1. A box around their face, labelled with their id and the strongest
   expression probability, e.g. "P1  neutral 0.61". The face box comes from
   s20_faces (already filtered there) and is kept for FACE_GRACE_SECONDS after
   the head points go missing, so it does not flicker.
2. Their one hand (the hand the gesture or raise-hand score is for, or their
   highest hand): the full MediaPipe skeleton (21 points and the lines between
   them) and a box around it, labelled with the task and score, e.g.
   "thumbs_up 0.82". The label colour shows where the score stands against the
   task's thresholds: green = success, orange = review band, grey = below.
3. A thin line from the hand's wrist to the bottom of the face box, so it is
   clear whose hand it is.

If a person's face is not visible, only the hand box is drawn and its label
starts with the person's id ("P1  thumbs_up 0.82").

The expression label is model output, shown as a probability. It is not an
emotional state. Detailed per-stage drawings are available with
CUES_OVERLAY=debug (vision.watch --debug).
"""

from __future__ import annotations

import cv2
import numpy as np

from vision import activities
from vision.activities import TASKS
from vision.grouping import GROUPING
from vision.people import person_color
from vision.session_sync import frame_activity
from vision.stages.s10_hands import CONNECTIONS

FACE_SMOOTHING = 0.35  # weight of a new face detection (they arrive only ~5 times a second)
FACE_GRACE_SECONDS = 0.5
FACE_DEAD_ZONE = 0.04  # a detection this close (x box size) to where the box is changes nothing
FACE_SIZE_RANGE = (0.85, 1.2)  # one detection can change the box size by at most this
FRAME_SCALE_RANGE = (0.9, 1.1)  # body-size change between frames used to scale the box
MOVE_DEAD_ZONE_PX = 0.8  # nose moves smaller than this are tracker noise
HAND_PADDING = 0.15
HAND_SMOOTHING = 0.5  # weight of the newest hand box
HAND_SIZE_RANGE = (0.85, 1.18)  # per frame; stops resizing when the hand crosses the face
HAND_BOX_GAP_SECONDS = 0.3  # a hand box older than this starts fresh
FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN, ORANGE, GREY, BLACK = (0, 190, 0), (0, 160, 255), (150, 150, 150), (0, 0, 0)


def short_id(pid: str) -> str:
    return pid.rsplit("-", 1)[-1]  # "S1-P1" -> "P1"


def score_color(activity_id: str, score: float | None) -> tuple[int, int, int]:
    if score is None:
        return GREY
    activity = activities.get(activity_id)
    if score >= activity.success_threshold:
        return GREEN
    if score >= activity.review_threshold:
        return ORANGE
    return GREY


def hand_box(landmarks: np.ndarray, w: int, h: int, pad: float = HAND_PADDING):
    xs, ys = landmarks[:, 0] * w, landmarks[:, 1] * h
    px, py = (xs.max() - xs.min()) * pad, (ys.max() - ys.min()) * pad
    return (int(xs.min() - px), int(ys.min() - py), int(xs.max() + px), int(ys.max() + py))


def smooth_box(old, new, weight: float, size_range: tuple[float, float]):
    """Move a box toward `new`, with its size allowed to change only a little at a time.

    The centre follows `new` by `weight`; width and height are first limited to
    `size_range` x the old size, then blended the same way. This stops a box from
    suddenly shrinking or growing when a detector is thrown off, for example when a
    hand covers part of a face.
    """
    ow, oh = old[2] - old[0], old[3] - old[1]
    nw, nh = new[2] - new[0], new[3] - new[1]
    nw = min(max(nw, ow * size_range[0]), ow * size_range[1])
    nh = min(max(nh, oh * size_range[0]), oh * size_range[1])
    ocx, ocy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
    ncx, ncy = (new[0] + new[2]) / 2, (new[1] + new[3]) / 2
    cx, cy = ocx + weight * (ncx - ocx), ocy + weight * (ncy - ocy)
    w, h = ow + weight * (nw - ow), oh + weight * (nh - oh)
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def label(image, text: str, x: int, y: int, fill) -> None:
    """Text on a filled tab whose bottom edge sits at y."""
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.5, 1)
    top = max(0, y - th - 8)
    cv2.rectangle(image, (x, top), (x + tw + 8, top + th + 8), fill, -1)
    cv2.putText(image, text, (x + 4, top + th + 3), FONT, 0.5, BLACK, 1, cv2.LINE_AA)


class OverlayStage:
    name = "overlay"
    rate_hz = None

    def __init__(self, grouping=GROUPING) -> None:
        self.grouping = grouping
        self._faces: dict[str, tuple[tuple[float, float, float, float], float]] = {}
        self._face_seen: dict[str, object] = {}  # the Face object last drawn per person
        # per person: (nose in pixels, shoulder width) as seen on the previous frame
        self._body_before: dict[str, tuple] = {}
        self._hand_boxes: dict[str, tuple[tuple[float, float, float, float], float]] = {}
        self._now = 0.0

    @staticmethod
    def _body(person, w: int, h: int):
        """(nose in pixels, shoulder width in frame heights); each None if not reliable."""
        if person is None:
            return None, None
        x, y, visibility = person.point(0)
        nose = (x * w, y * h) if visibility >= 0.5 else None
        _, _, lv = person.point(11)
        _, _, rv = person.point(12)
        width = person.shoulder_width if min(lv, rv) >= 0.5 else None
        return nose, width

    def process(self, frame, ctx) -> None:
        """Smooth face boxes and drop ones not seen for FACE_GRACE_SECONDS.

        Faces are detected only a few times a second, but the pose tracker runs
        every frame. Between face detections the box is moved by how far the
        person's nose moved, and scaled by how much their shoulders got bigger or
        smaller (walking toward or away from the camera). A new detection that is
        already close to the box changes nothing (so a still person's box is still);
        a bigger difference moves it only part of the way, and its size can change
        only a little per detection (so a hand over the face cannot shrink it).
        """
        t = frame.timestamp
        self._now = t
        h, w = frame.image.shape[:2]
        people = ctx.get("people", {})
        body = {pid: self._body(people.get(pid), w, h) for pid in set(self._faces) | set(people)}
        for pid, (box, seen) in list(self._faces.items()):
            (pn, pw), (cn, cw) = (
                self._body_before.get(pid, (None, None)),
                body.get(pid, (None, None)),
            )
            if pn is None or cn is None:
                continue
            dx, dy = cn[0] - pn[0], cn[1] - pn[1]
            if abs(dx) < MOVE_DEAD_ZONE_PX and abs(dy) < MOVE_DEAD_ZONE_PX:
                dx = dy = 0.0
            ratio = 1.0
            if pw and cw and abs(cw / pw - 1.0) > 0.01:
                ratio = min(max(cw / pw, FRAME_SCALE_RANGE[0]), FRAME_SCALE_RANGE[1])
            # Scale about the previous nose, then move with the nose.
            xs = [(box[i] - pn[0]) * ratio + pn[0] + dx for i in (0, 2)]
            ys = [(box[i] - pn[1]) * ratio + pn[1] + dy for i in (1, 3)]
            self._faces[pid] = ((xs[0], ys[0], xs[1], ys[1]), seen)
        self._body_before = body
        if "people" in ctx:  # the body tracker lost this person: their face box goes too
            for pid in [p for p in self._faces if p not in people]:
                del self._faces[pid]
        faces = ctx.get("faces", {})
        for pid, face in faces.items():
            fresh = self._face_seen.get(pid) is not face  # a new detection, not last one again
            self._face_seen[pid] = face
            if not fresh:
                continue  # the box keeps moving with the body; its age is not refreshed
            det = tuple(float(v) for v in face.box)
            old = self._faces.get(pid)
            if old is not None:
                ob = old[0]
                ow, oh = ob[2] - ob[0], ob[3] - ob[1]
                close = (
                    abs((det[0] + det[2]) / 2 - (ob[0] + ob[2]) / 2) < FACE_DEAD_ZONE * ow
                    and abs((det[1] + det[3]) / 2 - (ob[1] + ob[3]) / 2) < FACE_DEAD_ZONE * oh
                    and abs((det[2] - det[0]) - ow) < 2 * FACE_DEAD_ZONE * ow
                    and abs((det[3] - det[1]) - oh) < 2 * FACE_DEAD_ZONE * oh
                )
                det = ob if close else smooth_box(ob, det, FACE_SMOOTHING, FACE_SIZE_RANGE)
            if "people" not in ctx or pid in people:
                self._faces[pid] = (det, t)
        for pid in [p for p in self._face_seen if p not in faces]:
            del self._face_seen[pid]
        # Expire from the last real detection, so a box can't be held forever.
        for pid in [p for p, (_, seen) in self._faces.items() if t - seen > FACE_GRACE_SECONDS]:
            del self._faces[pid]
        for pid in [p for p, (_, seen) in self._hand_boxes.items() if t - seen > 1.0]:
            del self._hand_boxes[pid]  # people who left
        ctx["overlay_faces"] = {pid: box for pid, (box, _) in self._faces.items()}

    def _smooth_hand_box(self, pid: str, raw):
        """The hand box, steadied: its size changes only a little per frame."""
        raw = tuple(float(v) for v in raw)
        old = self._hand_boxes.get(pid)
        if old is not None and self._now - old[1] <= HAND_BOX_GAP_SECONDS:
            ob = old[0]
            size = max(ob[2] - ob[0], ob[3] - ob[1], 1.0)
            jump = max(
                abs((raw[0] + raw[2]) / 2 - (ob[0] + ob[2]) / 2),
                abs((raw[1] + raw[3]) / 2 - (ob[1] + ob[3]) / 2),
            )
            if jump <= size:  # a different hand or a real jump starts fresh
                raw = smooth_box(ob, raw, HAND_SMOOTHING, HAND_SIZE_RANGE)
        self._hand_boxes[pid] = (raw, self._now)
        return tuple(int(v) for v in raw)

    def draw(self, image, ctx) -> None:
        from vision import overlay

        if overlay.debug():
            return  # debug mode draws each stage's own detail instead
        h, w = image.shape[:2]
        faces = ctx.get("overlay_faces", {})
        labels = []  # drawn last, so hands never cover a label
        for pid in self.grouping.ids(ctx):
            color = person_color(pid)
            face = faces.get(pid)
            match = ctx.get("match", {}).get(pid)
            recognized = ctx.get("recognized", {}).get(pid)  # recognise mode only
            hand = match.hand if match is not None and match.hand is not None else None
            if recognized is not None and recognized.hand is not None:
                hand = recognized.hand
            if hand is None:  # no score yet: still show the person's highest hand
                person_hands = ctx.get("hands", {}).get(pid, [])
                hand = min(person_hands, key=lambda hd: hd.wrist[1]) if person_hands else None

            if face is not None:
                x0, y0, x1, y1 = (int(v) for v in face)
                cv2.rectangle(image, (x0, y0), (x1, y1), color, 2)
                text = short_id(pid)
                dist = ctx.get("expression", {}).get(pid)
                if dist:
                    top = max(dist, key=dist.get)
                    text += f"  {top} {dist[top]:.2f}"
                labels.append((text, x0, y0, color))

            if hand is not None:
                pts = [(int(x * w), int(y * h)) for x, y, _ in hand.landmarks]
                if face is not None:
                    fx = (int(face[0]) + int(face[2])) // 2
                    cv2.line(image, pts[0], (fx, int(face[3])), color, 1, cv2.LINE_AA)
                for a, b in CONNECTIONS:
                    cv2.line(image, pts[a], pts[b], color, 2)
                for p in pts:
                    cv2.circle(image, p, 3, color, -1)
                hx0, hy0, hx1, hy1 = self._smooth_hand_box(pid, hand_box(hand.landmarks, w, h))
                cv2.rectangle(image, (hx0, hy0), (hx1, hy1), color, 2)
                text = "" if face is not None else short_id(pid) + "  "
                fill = GREY
                from vision.gestures.hand_pose import palm_side

                side = palm_side(hand.landmarks, hand.handedness)
                # Only the selected task is checked: it alone can turn green. Any other
                # gesture the camera sees is shown in grey, however confident.
                task_id = (
                    match.activity_id if match is not None else frame_activity(TASKS, pid, ctx)
                )
                seen = recognized
                if (
                    seen is not None
                    and seen.activity_id is not None
                    and seen.activity_id == task_id
                ):
                    shown_score = "--" if seen.score is None else f"{seen.score:.2f}"
                    text += f"{seen.activity_id} {shown_score} ({side})"
                    # Green while the task is completed or still close to it (held
                    # through a dip); grey once the live score has really fallen away.
                    review = activities.get(seen.activity_id).review_threshold
                    done = seen.score is not None and seen.score >= review
                    fill = GREEN if done else GREY
                elif match is not None:  # progress on the selected task
                    score = "--" if match.score is None else f"{match.score:.2f}"
                    text += f"{match.activity_id} {score} ({side})"
                    fill = score_color(match.activity_id, match.score)
                else:
                    text += f"no gesture ({side})"
                labels.append((text.strip() or short_id(pid), hx0, hy0, fill))
                if (
                    seen is not None
                    and seen.activity_id is not None
                    and seen.activity_id != task_id
                ):
                    other = "--" if seen.score is None else f"{seen.score:.2f}"
                    labels.append((f"also seeing: {seen.activity_id} {other}", hx0, hy1 + 22, GREY))
                extra = ctx.get("all_scores", {}).get(pid)
                if extra:  # all-gestures readout (vision.all_scores), under the hand box
                    others = {a: v for a, v in extra.items() if a != task_id}
                    if others:
                        from vision.stages.s45_all_scores import format_scores

                        labels.append((format_scores(others), hx0, hy1 + 22, (210, 210, 210)))
            # With no hand in view there is no gesture label: a gesture's score belongs
            # to the hand, never to the face box.

        for text, x, y, fill in labels:
            label(image, text, x, y, fill)


def create_stage() -> OverlayStage:
    return OverlayStage()
