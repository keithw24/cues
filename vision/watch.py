"""Print what the vision pipeline sees, once a second, for each seat.

    uv run python -m vision.watch --all-on                 # webcam, all perception on
    uv run python -m vision.watch --all-on --task custom_gesture_01
    CUES_CAMERA=fake uv run python -m vision.watch --all-on --seconds 5

Output per seat:

    Seat: S1-L
    Task: thumbs_up
    Match score: 0.81
    Expression:
      neutral: 0.61
      happiness: 0.21
      sadness: 0.04

No events are sent: this only shows perception results.
"""

from __future__ import annotations

import argparse
import os
import time

PERCEPTION_FLAGS = ("vision.hands", "vision.faces", "vision.gestures", "vision.expression")


def format_seat(seat, task, match, expression, top: int = 3) -> str:
    lines = [f"Seat: {seat}", f"Task: {task}"]
    if match is None:
        lines.append("Match score: -- (no hand in this seat)")
    elif match.score is None:
        lines.append(f"Match score: -- ({match.reason})")
    else:
        lines.append(f"Match score: {match.score:.2f}")
    if not expression:
        lines.append("Expression: -- (no face in this seat)")
    else:
        lines.append("Expression:")
        for label, p in sorted(expression.items(), key=lambda kv: -kv[1])[:top]:
            lines.append(f"  {label}: {p:.2f}")
    return "\n".join(lines)


def format_snapshot(ctx, seat_ids, tasks, top: int = 3) -> str:
    blocks = []
    for seat in seat_ids:
        task = tasks.for_seat(seat)
        match = ctx.get("match", {}).get(seat)
        expression = ctx.get("expression", {}).get(seat)
        blocks.append(format_seat(seat, task, match, expression, top))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print per-seat perception results.")
    parser.add_argument(
        "--all-on",
        action="store_true",
        help="turn on hands, faces, gestures and expression for this run",
    )
    parser.add_argument("--task", help="current task for both seats (default: CUES_TASK)")
    parser.add_argument("--seconds", type=float, help="stop after this many seconds")
    parser.add_argument("--top", type=int, default=3, help="expression labels to show (max 8)")
    args = parser.parse_args(argv)

    if args.all_on:
        from vision import flags

        for name in PERCEPTION_FLAGS:
            os.environ[flags.env_name(name)] = "1"

    from vision import flags
    from vision.activities import TASKS
    from vision.camera import camera_from_env
    from vision.pipeline import Pipeline, discover_stages
    from vision.seats import ZONES

    if args.task:
        TASKS.set_class_task(args.task)
    off = [n for n in PERCEPTION_FLAGS if not flags.enabled(n)]
    if off:
        print(f"Off: {', '.join(off)}. Use --all-on or set CUES_FLAG_* to turn them on.\n")

    pipeline = Pipeline(camera_from_env(), discover_stages())
    print("Starting camera and models (first run downloads models)...", flush=True)
    pipeline.start()
    started = time.monotonic()
    try:
        while args.seconds is None or time.monotonic() - started < args.seconds:
            time.sleep(1.0)
            print("\033[2J\033[H" if os.isatty(1) else "-" * 40 + "\n", end="")
            print(format_snapshot(pipeline.ctx, ZONES.seat_ids, TASKS, args.top), flush=True)
            print(f"\n[{pipeline.health()['fps']} fps]", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
