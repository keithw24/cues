"""Record gesture examples from the webcam.

Records about 2 seconds of hand poses and adds them to the activity's
examples in vision/templates/ (stored only on this laptop). Run with the
vision service stopped, since only one process can use the camera.

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

from vision.gestures import templates as tpl
from vision.gestures.matcher import calibrate_rejection
from vision.gestures.normalize import normalize


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


def drain(cap, seconds: float) -> None:
    """Keep reading frames for `seconds` so the next read is a fresh frame."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        cap.grab()


def record_take(
    cap, detector, seconds: float, fps: float, seat: str | None, zones
) -> tuple[list, int]:
    """Returns (hand vectors, number of frames looked at)."""
    import mediapipe as mp

    from vision.stages.s10_hands import hands_from_result

    vectors = []
    frames = 0
    end = time.monotonic() + seconds
    period = 1.0 / fps
    while time.monotonic() < end:
        ok, bgr = cap.read()
        if not ok:
            continue
        frames += 1
        rgb = cv2.cvtColor(cv2.resize(bgr, (640, 480)), cv2.COLOR_BGR2RGB)
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        hand = pick_hand(hands_from_result(result, zones), seat)
        if hand is not None:
            vectors.append(normalize(hand.landmarks, hand.handedness))
        time.sleep(period)
    return vectors, frames


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
    args = parser.parse_args(argv)

    activity = activities.get(args.activity_id)
    if activity.check_type != "gesture":
        raise SystemExit(f"{activity.id} is a {activity.check_type} task; nothing to record")

    detector = models.hand_landmarker(num_hands=4)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open the camera. Is the vision service running?")
    templates = tpl.load(activity.id)
    zones = recording_zones(args.seat)
    try:
        drain(cap, 1.0)  # camera warm-up: the first frames are often dark
        for remaining in range(args.delay, 0, -1):
            print(f"Get ready: recording starts in {remaining}s...", flush=True)
            drain(cap, 1.0)
        for take in range(1, args.takes + 1):
            for n in (3, 2, 1):
                print(f"Take {take}/{args.takes}: show '{args.label}' in {n}...", flush=True)
                drain(cap, 1.0)
            print("Recording...", flush=True)
            vectors, frames = record_take(cap, detector, args.seconds, args.fps, args.seat, zones)
            print(f"  captured {len(vectors)} hand poses from {frames} frames")
            if not vectors:
                print("  No hand found. Keep the whole hand in view, closer and well lit.")
            templates.add(args.label, vectors)
    finally:
        cap.release()

    path = tpl.save(templates)
    target, rest = templates.arrays()
    print(f"\nSaved {path}: {len(target)} target, {len(rest)} rest examples.")
    if len(target):
        print(f"Calibrated rejection threshold: {calibrate_rejection(target):.3f}")
    if len(target) and not len(rest):
        print("Tip: record some 'rest' examples too, so other hand shapes score low.")


if __name__ == "__main__":
    main()
