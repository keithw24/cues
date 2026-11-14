"""Record gesture examples from the webcam.

Records about 2 seconds of hand poses and adds them to the activity's
examples in vision/templates/ (stored only on this laptop). Run with the
vision service stopped, since only one process can use the camera.

A preview window shows the camera (mirrored, like a selfie) with your hand
drawn in green when it is detected. Press q in the window to cancel.

    uv run python -m vision.record thumbs_up target          # the gesture
    uv run python -m vision.record thumbs_up rest            # relaxed / other hands
    uv run python -m vision.record custom_gesture_01 target --seat S1-L --takes 3
    uv run python -m vision.record thumbs_up target --delay 0   # skip the 10 s wait

Record 3-5 takes of the target and at least 2 of rest, varying the hand a
little (angle, distance) between takes.
"""

from __future__ import annotations

import argparse
import time

import cv2
import numpy as np

from vision.camera import standard_frame
from vision.gestures import templates as tpl
from vision.gestures.matcher import calibrate_rejection
from vision.gestures.normalize import normalize

WINDOW = "Cues recorder (press q to cancel)"
GREEN, RED, WHITE = (0, 200, 0), (0, 0, 230), (255, 255, 255)


def pick_hand(by_seat: dict, seat: str | None):
    if seat is not None:
        hands = by_seat.get(seat, [])
    else:
        hands = [h for hs in by_seat.values() for h in hs]
    if not hands:
        return None
    # The hand with the largest spread is the one closest to the camera.
    return max(hands, key=lambda h: float(np.ptp(h.landmarks[:, :2], axis=0).prod()))


def recording_zones(seat: str | None):
    """Seat zones for recording.

    Without --seat, keep every hand: no dead band, so a hand in the middle of
    the frame (where a single person usually holds it) is not thrown away.
    With --seat, use the service's normal zones so only that seat counts.
    """
    from vision.seats import ZONES, SeatZones

    if seat is None:
        return SeatZones(station_id=ZONES.station_id, divider=ZONES.divider, dead_band=0.0)
    return ZONES


class Cancelled(Exception):
    """The user pressed q in the preview window."""


class Recorder:
    """Reads the camera, finds the hand, shows a live preview, collects poses."""

    def __init__(self, cap, detector, zones, seat: str | None, preview: bool = True) -> None:
        self.cap = cap
        self.detector = detector
        self.zones = zones
        self.seat = seat
        self.preview = preview

    def run(self, seconds: float, banner: str, record: bool = False, fps: float = 10.0):
        """Show the camera for `seconds`; if `record`, collect hand vectors.

        Returns (hand vectors, frames looked at).
        """
        import mediapipe as mp

        from vision.stages.s10_hands import hands_from_result

        vectors, frames = [], 0
        end = time.monotonic() + seconds
        next_sample = 0.0
        while (now := time.monotonic()) < end:
            ok, bgr = self.cap.read()
            if not ok:
                continue
            frames += 1
            bgr = standard_frame(bgr)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = self.detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            hand = pick_hand(hands_from_result(result, self.zones), self.seat)
            if record and hand is not None and now >= next_sample:
                vectors.append(normalize(hand.landmarks, hand.handedness))
                next_sample = now + 1.0 / fps
            if self.preview:
                self.show(bgr, hand, f"{banner} {end - now:.0f}s", record, len(vectors))
        return vectors, frames

    def show(self, bgr, hand, banner: str, record: bool, captured: int) -> None:
        from vision.stages.s10_hands import CONNECTIONS

        image = bgr.copy()
        h, w = image.shape[:2]
        if hand is not None:
            pts = [(int(x * w), int(y * h)) for x, y, _ in hand.landmarks]
            for a, b in CONNECTIONS:
                cv2.line(image, pts[a], pts[b], GREEN, 2)
            for pt in pts:
                cv2.circle(image, pt, 3, GREEN, -1)
        image = cv2.flip(image, 1)  # mirror view, like a selfie camera
        found = hand is not None
        status = "HAND FOUND" if found else "NO HAND - move it into view"
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.rectangle(image, (0, 0), (w, 64), (30, 30, 30), -1)
        cv2.putText(image, banner, (10, 26), font, 0.7, RED if record else WHITE, 2)
        cv2.putText(image, status, (10, 54), font, 0.6, GREEN if found else RED, 2)
        if record:
            cv2.circle(image, (w - 24, 24), 10, RED, -1)
            cv2.putText(image, f"{captured} poses", (w - 150, 54), font, 0.6, WHITE, 1)
        cv2.imshow(WINDOW, image)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            raise Cancelled

    def close(self) -> None:
        if self.preview:
            cv2.destroyAllWindows()
            cv2.waitKey(1)


def main(argv: list[str] | None = None) -> None:
    from vision import activities, models

    parser = argparse.ArgumentParser(description="Record gesture examples from the webcam.")
    parser.add_argument("activity_id")
    parser.add_argument("label", choices=tpl.LABELS)
    parser.add_argument("--takes", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--seat", help="only use hands in this seat, e.g. S1-L")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument(
        "--delay", type=int, default=10, help="seconds to get ready before the first take"
    )
    parser.add_argument(
        "--no-preview", action="store_true", help="don't open the live camera window"
    )
    args = parser.parse_args(argv)

    activity = activities.get(args.activity_id)
    if activity.check_type != "gesture":
        raise SystemExit(f"{activity.id} is a {activity.check_type} task; nothing to record")

    detector = models.hand_landmarker(num_hands=4)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open the camera. Is the vision service running?")
    # Same request as the vision service, so recorded and live frames match.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    templates = tpl.load(activity.id)
    rec = Recorder(cap, detector, recording_zones(args.seat), args.seat, not args.no_preview)
    if rec.preview:
        print("A camera window opens: check your hand is in view and drawn in green.")
    try:
        rec.run(1.0, "Starting camera...")  # warm-up: the first frames are often dark
        print(f"Get ready: {args.delay}s", flush=True)
        rec.run(args.delay, "Get ready")
        for take in range(1, args.takes + 1):
            print(f"Take {take}/{args.takes}: show '{args.label}'", flush=True)
            rec.run(3.0, f"Take {take}/{args.takes}: '{args.label}' in")
            print("Recording...", flush=True)
            vectors, frames = rec.run(
                args.seconds, f"RECORDING take {take}", record=True, fps=args.fps
            )
            print(f"  captured {len(vectors)} hand poses from {frames} frames")
            if not vectors:
                print("  No hand found. Keep the whole hand in view, closer and well lit.")
            templates.add(args.label, vectors)
    except (Cancelled, KeyboardInterrupt):
        print("\nCancelled. Nothing was saved.")
        return
    finally:
        cap.release()
        rec.close()

    path = tpl.save(templates)
    target, rest = templates.arrays()
    print(f"\nSaved {path}: {len(target)} target, {len(rest)} rest examples.")
    if len(target):
        print(f"Calibrated rejection threshold: {calibrate_rejection(target, rest):.3f}")
    if len(target) and not len(rest):
        print("Tip: record some 'rest' examples too, so other hand shapes score low.")


if __name__ == "__main__":
    main()
