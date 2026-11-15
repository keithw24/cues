"""Teacher-only notification boundary; transport is supplied by backend setup."""

import json
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import dotenv_values

from agent.teacher_review import TeacherReview


class NotificationUnavailable(RuntimeError):
    """A send that could not happen, with a fixed reason that is safe to log
    (no phone number, secret or provider payload)."""


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


def _is_spectrum_setting(name: str) -> bool:
    return name.startswith("SPECTRUM_") or name == "CUES_USE_STATIC_TEACHER_PHONE"


def current_spectrum_config(startup: dict, root: Path) -> dict:
    """The startup config with cues/.env read again, so a long-running worker
    picks up Photon credentials saved after it started. Process environment
    (which also holds the root .env the worker loads) still wins."""
    config = dict(startup)
    path = root / "cues/.env"
    if path.is_file():
        config.update(
            {
                k: v
                for k, v in dotenv_values(path).items()
                if _is_spectrum_setting(k) and v is not None and v.strip()
            }
        )
    config.update({k: v for k, v in os.environ.items() if _is_spectrum_setting(k) and v.strip()})
    return config


def spectrum_notifier(startup_config: dict, root: Path, client=None) -> ReviewNotifier:
    """Always returns a notifier. Credentials are checked on each send, not at
    startup, so missing configuration fails loudly per review instead of
    silently disabling notifications until the worker restarts."""
    names = ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET")

    class SpectrumNotifier:
        def notify_pending_review(self, review: TeacherReview) -> None:
            if review.status != "pending":
                raise ValueError("only pending reviews may notify")
            config = current_spectrum_config(startup_config, root)
            if not all(config.get(name) for name in names):
                raise NotificationUnavailable(
                    "Spectrum project credentials are missing: set SPECTRUM_PROJECT_ID "
                    "and SPECTRUM_PROJECT_SECRET in cues/.env"
                )
            mode = str(config.get("CUES_USE_STATIC_TEACHER_PHONE", "0"))
            if mode not in ("0", "1"):
                raise NotificationUnavailable("CUES_USE_STATIC_TEACHER_PHONE must be 0 or 1")
            if mode == "1":
                phone = config.get("SPECTRUM_TEACHER_PHONE")
            else:
                if client is None:
                    raise NotificationUnavailable(
                        "Dynamic teacher routing requires a backend client"
                    )
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
                        raise NotificationUnavailable("Session has no teacher owner")
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
                    raise NotificationUnavailable("Teacher destination lookup failed") from None
            import re

            if not isinstance(phone, str) or not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
                raise NotificationUnavailable(
                    "Teacher profile/static destination requires an E.164 phone"
                )
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
                raise NotificationUnavailable(
                    "Spectrum did not acknowledge notification acceptance"
                )

    return SpectrumNotifier()
