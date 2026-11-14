"""Local demo model injection for the continuous SeatState runtime."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from agent.runtime import create_seat_state_runtime
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT
from vision.activities import load_activities


def main():
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
    create_seat_state_runtime(model, activities).run_forever()


if __name__ == "__main__":
    main()
