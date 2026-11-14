"""Print what the vision pipeline sees, once a second, for each seat.

    uv run python -m vision.watch --all-on                 # webcam + overlay window
    uv run python -m vision.watch --all-on --no-window     # text only
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

With vision.task_status on (it is, with --all-on), status changes are sent as
events to vision/logs/*.jsonl, or to Supabase when vision.supabase_events is on,
and the most recent ones are printed under "Recent events".
"""

from __future__ import annotations

import argparse
import os
import time

PERCEPTION_FLAGS = (
    "vision.hands",
    "vision.faces",
    "vision.gestures",
    "vision.raise_hand",
    "vision.expression",
    "vision.task_status",
    "vision.all_scores",
)


def format_seat(
    seat,
    task,
    match,
    expression,
    top: int = 3,
    debug: bool = False,
    all_scores=None,
    recognized=None,
) -> str:
    lines = [f"Seat: {seat}", f"Task: {task}"]
    if match is None:
        lines.append("Match score: -- (no hand detected)")
    elif match.score is None:
        lines.append(f"Match score: -- ({match.reason})")
    else:
        lines.append(f"Match score: {match.score:.2f}")
        if debug and match.detail:
            lines.append(f"  ({match.detail})")
    if recognized is not None:
        if recognized.activity_id is None:
            lines.append("Recognised: no gesture")
        else:
            lines.append(f"Recognised: {recognized.activity_id} {recognized.score:.2f}")
        if recognized.hand is not None:  # always shown
            from vision.gestures.hand_pose import describe

            hand = recognized.hand
            lines.append(f"Hand: {describe(hand.landmarks, hand.handedness)}")
        else:
            lines.append("Hand: none detected")
    if all_scores:
        from vision.stages.s45_all_scores import format_scores

        lines.append(f"All gestures: {format_scores(all_scores)}")
    if not expression:
        lines.append("Expression: -- (no face detected)")
    else:
        lines.append("Expression:")
        for label, p in sorted(expression.items(), key=lambda kv: -kv[1])[:top]:
            lines.append(f"  {label}: {p:.2f}")
    return "\n".join(lines)


def format_snapshot(ctx, seat_ids, tasks, top: int = 3, debug: bool = False) -> str:
    blocks = [] if seat_ids else ["No people detected yet."]
    for seat in seat_ids:
        task = tasks.for_seat(seat)
        status = ctx.get("status", {}).get(seat)
        if status:
            task = f"{task}  [{status}]"
        match = ctx.get("match", {}).get(seat)
        expression = ctx.get("expression", {}).get(seat)
        all_scores = ctx.get("all_scores", {}).get(seat)
        recognized = ctx.get("recognized", {}).get(seat)
        blocks.append(
            format_seat(seat, task, match, expression, top, debug, all_scores, recognized)
        )
    events = ctx.get("events", [])
    if events:
        blocks.append("Recent events:\n" + "\n".join(f"  {e}" for e in events[-8:]))
    return "\n\n".join(blocks)


class CameraWindow:
    """Shows the pipeline's annotated frames (the same image as /stream) in a window."""

    TITLE = "Cues vision (press q to quit)"

    def show(self, jpeg: bytes) -> bool:
        """Draw one frame. Returns False when the user presses q or closes the window."""
        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        cv2.imshow(self.TITLE, image)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return False
        try:
            return cv2.getWindowProperty(self.TITLE, cv2.WND_PROP_VISIBLE) >= 1
        except cv2.error:
            return False

    def close(self) -> None:
        import cv2

        cv2.destroyAllWindows()
        cv2.waitKey(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print per-seat perception results.")
    parser.add_argument(
        "--all-on",
        action="store_true",
        help="turn on all perception stages for this run",
    )
    parser.add_argument("--task", help="current task for everyone (default: CUES_TASK)")
    parser.add_argument("--seconds", type=float, help="stop after this many seconds")
    parser.add_argument("--top", type=int, default=3, help="expression labels to show (max 8)")
    parser.add_argument("--debug", action="store_true", help="show raw gesture distances")
    parser.add_argument(
        "--debug-overlay",
        action="store_true",
        help="draw every stage's own detail on the video instead of the normal overlay",
    )
    parser.add_argument(
        "--no-window", action="store_true", help="don't open the camera window with overlays"
    )
    args = parser.parse_args(argv)

    if args.debug_overlay:
        os.environ["CUES_OVERLAY"] = "debug"
    if args.all_on:
        from vision import flags

        for name in PERCEPTION_FLAGS:
            os.environ[flags.env_name(name)] = "1"

    from vision import flags
    from vision.activities import TASKS
    from vision.camera import camera_from_env
    from vision.grouping import GROUPING
    from vision.pipeline import Pipeline, discover_stages

    if args.task:
        if flags.enabled("vision.session_lifecycle"):
            parser.error(
                "--task cannot override a teacher-managed session; "
                "disable vision.session_lifecycle for local testing"
            )
        TASKS.set_class_task(args.task)
    off = [n for n in PERCEPTION_FLAGS if not flags.enabled(n)]
    if off:
        print(f"Off: {', '.join(off)}. Use --all-on or set CUES_FLAG_* to turn them on.\n")

    from vision.activity_sync import sync_from_env

    sync = None if args.task else sync_from_env()  # --task wins over the app
    if sync is not None:
        sync.start()
    pipeline = Pipeline(camera_from_env(), discover_stages())
    print("Starting camera and models (first run downloads models)...", flush=True)
    pipeline.start()
    window = None if args.no_window else CameraWindow()
    started = time.monotonic()
    next_print = started + 1.0
    frame_index = 0
    try:
        while args.seconds is None or time.monotonic() - started < args.seconds:
            if window is not None:
                # Show every new annotated frame; the text summary still prints once a second.
                frame_index, jpeg = pipeline.wait_for_jpeg(after=frame_index, timeout=0.1)
                if jpeg is not None and not window.show(jpeg):
                    break  # q pressed or window closed
            else:
                time.sleep(0.1)
            if time.monotonic() >= next_print:
                next_print += 1.0
                print("\033[2J\033[H" if os.isatty(1) else "-" * 40 + "\n", end="")
                snap = format_snapshot(
                    pipeline.ctx, GROUPING.ids(pipeline.ctx), TASKS, args.top, args.debug
                )
                print(snap, flush=True)
                print(f"\n[{pipeline.health()['fps']} fps]", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        if sync is not None:
            sync.stop()
        if window is not None:
            window.close()


if __name__ == "__main__":
    main()
