"""Laptop benchmark: can this laptop run hands + faces + expression fast enough?

Runs MediaPipe Hand Landmarker, the MediaPipe face detector and HSEmotion on
the same frames, times each one, and prints:

  * per-model latency (mean and 95th percentile) and the fps it could reach alone;
  * "all together": the fps if every model ran on every frame;
  * "PRD schedule": the fps with the planned rates (hands every frame,
    faces ~5 Hz, expression ~3 Hz for each of 2 people).

Usage (from the repo root):

    uv run python -m vision.bench              # webcam, 30 s
    uv run python -m vision.bench --seconds 10 --camera 1
    uv run python -m vision.bench --video clip.mp4
    uv run python -m vision.bench --fake       # synthetic frames

Answers PRD open question 1. Synthetic frames contain no hands or faces, so
only the real camera gives realistic numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from vision.camera import standard_frame

FACE_HZ = 5.0
EXPRESSION_HZ = 3.0
SEATS = 2


@dataclass
class Timing:
    name: str
    runs: int
    mean_ms: float
    p95_ms: float
    solo_fps: float


def summarize(name: str, samples_ms: list[float]) -> Timing:
    if not samples_ms:
        return Timing(name, 0, 0.0, 0.0, 0.0)
    ordered = sorted(samples_ms)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    mean = statistics.fmean(samples_ms)
    return Timing(name, len(samples_ms), mean, p95, 1000.0 / mean if mean > 0 else 0.0)


def schedule_fps(hands_ms: float, faces_ms: float, expr_ms: float, base_fps: float) -> float:
    """Estimated loop fps with the PRD's per-model rates.

    Per second of video the CPU spends: hands on every frame, faces FACE_HZ
    times, and expression EXPRESSION_HZ times per seat. Solve for the frame
    rate at which that budget fills one second, capped by the camera rate.
    """
    fixed_ms_per_s = faces_ms * FACE_HZ + expr_ms * EXPRESSION_HZ * SEATS
    remaining = 1000.0 - fixed_ms_per_s
    if remaining <= 0:
        return 0.0
    if hands_ms <= 0:
        return base_fps
    return min(base_fps, remaining / hands_ms)


def frames(args: argparse.Namespace) -> Iterator[np.ndarray]:
    deadline = time.monotonic() + args.seconds
    if args.fake:
        rng = np.random.default_rng(0)
        while time.monotonic() < deadline:
            yield rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
        return
    cap = cv2.VideoCapture(args.video if args.video else args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open the camera/video. Check permissions or --camera index.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    try:
        while time.monotonic() < deadline:
            ok, image = cap.read()
            if not ok:
                if args.video:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            yield standard_frame(image)
    finally:
        cap.release()


def face_crop(rgb: np.ndarray, detection) -> np.ndarray:
    h, w = rgb.shape[:2]
    if detection is None:
        # No face: time HSEmotion on a centre crop so its cost is still measured.
        return rgb[h // 2 - 112 : h // 2 + 112, w // 2 - 112 : w // 2 + 112]
    box = detection.bounding_box
    x0, y0 = max(0, box.origin_x), max(0, box.origin_y)
    x1, y1 = min(w, x0 + box.width), min(h, y0 + box.height)
    crop = rgb[y0:y1, x0:x1]
    return crop if crop.size else rgb[:224, :224]


def run(args: argparse.Namespace) -> dict:
    import mediapipe as mp

    from vision import models

    print("Loading models (first run downloads them)...")
    hands = models.hand_landmarker(num_hands=4)
    faces = models.face_detector()
    expr = models.expression_recognizer()

    t_hands: list[float] = []
    t_faces: list[float] = []
    t_expr: list[float] = []
    t_total: list[float] = []
    hands_seen = faces_seen = 0
    camera_frames = 0
    started = time.monotonic()

    for bgr in frames(args):
        camera_frames += 1
        t0 = time.perf_counter()
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        a = time.perf_counter()
        hand_result = hands.detect(image)
        b = time.perf_counter()
        face_result = faces.detect(image)
        c = time.perf_counter()
        detection = face_result.detections[0] if face_result.detections else None
        expr.predict_emotions(face_crop(rgb, detection), logits=False)
        d = time.perf_counter()

        t_hands.append((b - a) * 1000)
        t_faces.append((c - b) * 1000)
        t_expr.append((d - c) * 1000)
        t_total.append((d - t0) * 1000)
        hands_seen += bool(hand_result.hand_landmarks)
        faces_seen += detection is not None

    elapsed = time.monotonic() - started
    timings = [
        summarize("hands (MediaPipe Hand Landmarker)", t_hands),
        summarize("faces (MediaPipe face detector)", t_faces),
        summarize("expression (HSEmotion enet_b0_8)", t_expr),
        summarize("all together, every frame", t_total),
    ]
    base_fps = camera_frames / elapsed if elapsed > 0 else 0.0
    sched = schedule_fps(timings[0].mean_ms, timings[1].mean_ms, timings[2].mean_ms, 30.0)
    return {
        "frames": camera_frames,
        "frames_with_hands": hands_seen,
        "frames_with_face": faces_seen,
        "timings": [asdict(t) for t in timings],
        "measured_loop_fps": round(base_fps, 1),
        "prd_schedule_fps_estimate": round(sched, 1),
    }


def print_report(report: dict) -> None:
    print(
        f"\nFrames: {report['frames']}  (hands seen in {report['frames_with_hands']}, "
        f"a face in {report['frames_with_face']})\n"
    )
    print(f"{'model':<36}{'mean ms':>9}{'p95 ms':>9}{'solo fps':>10}")
    for t in report["timings"]:
        print(f"{t['name']:<36}{t['mean_ms']:>9.1f}{t['p95_ms']:>9.1f}{t['solo_fps']:>10.1f}")
    print(f"\nMeasured fps, all models on every frame: {report['measured_loop_fps']}")
    print(
        f"Estimated fps with the PRD schedule (faces {FACE_HZ:g} Hz, expression "
        f"{EXPRESSION_HZ:g} Hz x {SEATS} people): {report['prd_schedule_fps_estimate']}"
    )
    verdict = "OK" if report["prd_schedule_fps_estimate"] >= 5 else "TOO SLOW"
    print(f"Target >= 5 fps end to end: {verdict}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--video", help="benchmark on a video file instead of the camera")
    parser.add_argument("--fake", action="store_true", help="synthetic frames, no camera")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
