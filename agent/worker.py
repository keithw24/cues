"""Local demo model injection for the continuous SeatState runtime."""

import argparse
import logging
import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from agent.escalation import DEMO_ESCALATION_CONFIG
from agent.progress import DEMO_PROGRESS_WINDOW_SECONDS
from agent.runtime import create_seat_state_runtime
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT
from vision.activities import load_activities


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("dev", "demo"), default="dev")
    profile = parser.parse_args().profile
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # Keep transition diagnostics readable; request URLs/tool payloads are not needed.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_dotenv(REPO_ROOT / ".env")
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Configure root .env: " + ", ".join(required))
    activities = [
        Activity(
            id=a.id,
            name=a.name,
            check_type=a.check_type,
            no_progress_seconds=a.no_progress_seconds,
            success_threshold=a.success_threshold,
            review_threshold=a.review_threshold,
        )
        for a in load_activities().values()
    ]
    model = ChatGroq(model="openai/gpt-oss-20b", temperature=0, timeout=20, max_retries=2)
    options = {}
    if profile == "demo":
        options = dict(
            progress_window_seconds=DEMO_PROGRESS_WINDOW_SECONDS,
            escalation_config=DEMO_ESCALATION_CONFIG,
            # Vision publishes at ~1 Hz. Poll faster than that heartbeat so
            # request latency does not turn skipped rows into >2s tracking gaps.
            poll_seconds=0.5,
        )
    from agent.escalation import DEFAULT_ESCALATION_CONFIG

    timing = options.get("escalation_config", DEFAULT_ESCALATION_CONFIG)
    logging.info(
        "Agent profile=%s window=%ss minimum=%ss normal=%ss expression=%ss prolonged=%ss poll=%ss",
        profile,
        options.get("progress_window_seconds", 4),
        timing.min_observation_seconds,
        timing.normal_stall_seconds,
        timing.expression_assisted_seconds,
        timing.prolonged_stall_seconds,
        options.get("poll_seconds", 1.0),
    )
    options["publish_progress"] = True

    from agent.notifications import current_spectrum_config, spectrum_env

    spectrum = current_spectrum_config({}, REPO_ROOT / "cues/.env", spectrum_env())
    if not all(spectrum.get(n) for n in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET")):
        # Not fatal: cues/.env is read again on every send, so saving it later is enough.
        logging.warning(
            "Teacher text alerts: cues/.env has no SPECTRUM_PROJECT_ID/SECRET yet; "
            "alerts fail until it is saved (no restart needed)"
        )
    else:
        logging.info("Teacher text alerts: on")
    create_seat_state_runtime(model, activities, **options).run_forever()


if __name__ == "__main__":
    main()
