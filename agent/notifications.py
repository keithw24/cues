"""Teacher-only notification boundary; transport is supplied by backend setup."""

import json
import logging
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


def spectrum_notifier(config: dict, root: Path, client=None) -> ReviewNotifier | None:
    names = ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET")
    if not any(config.get(name) for name in names):
        return None
    mode = str(config.get("CUES_USE_STATIC_TEACHER_PHONE", "0"))
    if mode not in ("0", "1"):
        raise ValueError("CUES_USE_STATIC_TEACHER_PHONE must be 0 or 1")

    class SpectrumNotifier:
        def notify_pending_review(self, review: TeacherReview) -> None:
            if review.status != "pending":
                raise ValueError("only pending reviews may notify")
            if not all(config.get(name) for name in names):
                raise RuntimeError("Spectrum project credentials are required")
            if mode == "1":
                phone = config.get("SPECTRUM_TEACHER_PHONE")
            else:
                if client is None:
                    raise RuntimeError("Dynamic teacher routing requires a backend client")
                try:
                    sessions = (
                        client.table("sessions")
                        .select("teacher_id")
                        .eq("id", str(review.evaluation.session_id))
                        .execute()
                        .data
                    )
                    owner = sessions[0].get("teacher_id") if sessions else None
                    if not owner:
                        raise RuntimeError("Session has no teacher owner")
                    from agent.notification_activation import send_to_teacher

                    status = send_to_teacher(
                        client,
                        config,
                        root,
                        owner,
                        f"Cues: Seat {review.evaluation.seat_id} may need attention. "
                        "Open Cues to review.",
                    )
                    if status == "pending":
                        logging.getLogger(__name__).warning(
                            "Teacher notification activating: target_not_allowed"
                        )
                    return
                except RuntimeError:
                    raise
                except Exception:
                    raise RuntimeError("Teacher destination lookup failed") from None
            import re

            if not isinstance(phone, str) or not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
                raise RuntimeError("Teacher profile/static destination requires an E.164 phone")
            env = dict(os.environ)
            for credential in ("PHOTON_TOKEN", "DASHBOARD_TOKEN"):
                env.pop(credential, None)
            # Remove inherited static destination even when the nested env contains one.
            env.pop("SPECTRUM_TEACHER_PHONE", None)
            env["CUES_USE_STATIC_TEACHER_PHONE"] = mode
            for name in (*names, "SPECTRUM_SENDER_PHONE"):
                if config.get(name):
                    env[name] = config[name]
            if mode == "1":
                env["SPECTRUM_TEACHER_PHONE"] = phone
            result = subprocess.run(
                [str(root / "cues/node_modules/.bin/tsx"), str(root / "cues/src/notify.ts")],
                input=json.dumps(
                    {
                        "message": (
                            f"Cues: Seat {review.evaluation.seat_id} may need attention. "
                            "Open Cues to review."
                        ),
                        "review_id": str(review.id),
                        "destination": phone if mode == "0" else None,
                    }
                ),
                text=True,
                capture_output=True,
                env=env,
                timeout=25,
            )
            if result.returncode or not result.stdout.strip().endswith('{"accepted":true}'):
                raise RuntimeError("Spectrum did not acknowledge notification acceptance")

    return SpectrumNotifier()
