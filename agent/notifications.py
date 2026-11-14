"""Teacher-only notification boundary; transport is supplied by backend setup."""

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from agent.teacher_review import TeacherReview


class ReviewNotifier(Protocol):
    def notify_pending_review(self, review: TeacherReview) -> None: ...


class PhotonNotifier:
    """Adapter for an injected Photon sender, without guessing a sponsor API.

    send(message, review_id) must raise on failed delivery. The review ID is a
    transport idempotency key, not part of the teacher-visible message.
    """

    def __init__(self, send: Callable[[str, str], None]):
        self._send = send

    def notify_pending_review(self, review: TeacherReview) -> None:
        if review.status != "pending":
            raise ValueError("only pending reviews may notify")
        self._send(
            f"Cues: Seat {review.evaluation.seat_id} may need attention. Open Cues to review.",
            str(review.id),
        )


def spectrum_notifier(config: dict, root: Path) -> PhotonNotifier | None:
    names = ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET", "SPECTRUM_TEACHER_PHONE")
    if not any(config.get(name) for name in names):
        return None

    def send(message: str, review_id: str) -> None:
        if not all(config.get(name) for name in names):
            raise RuntimeError("Spectrum credentials and teacher destination are required")
        env = dict(os.environ)
        for name in (*names, "SPECTRUM_SENDER_PHONE"):
            if config.get(name):
                env[name] = config[name]
        result = subprocess.run(
            [str(root / "cues/node_modules/.bin/tsx"), str(root / "cues/src/notify.ts")],
            input=json.dumps({"message": message, "review_id": review_id}),
            text=True,
            capture_output=True,
            env=env,
            timeout=25,
        )
        if result.returncode or not result.stdout.strip().endswith('{"accepted":true}'):
            raise RuntimeError("Spectrum did not acknowledge notification acceptance")

    return PhotonNotifier(send)
