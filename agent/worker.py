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
    load_dotenv(REPO_ROOT / ".env")
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY", "CUES_SESSION_ID")
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
        )
    from dotenv import dotenv_values

    if not all(
        os.environ.get(name) or dotenv_values(REPO_ROOT / "cues/.env").get(name)
        for name in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET")
    ):
        logging.warning("Spectrum configuration missing/incomplete; notifications disabled")

        class DisabledNotifier:
            def notify_pending_review(self, review):
                logging.warning("Pending review persisted; Spectrum notification unavailable")

        options["notifier"] = DisabledNotifier()
    create_seat_state_runtime(model, activities, **options).run_forever()


if __name__ == "__main__":
    main()
