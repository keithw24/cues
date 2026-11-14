"""Local demo model injection for the continuous SeatState runtime."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from agent.runtime import create_seat_state_runtime
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT, get_client


def main():
    load_dotenv(REPO_ROOT / ".env")
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY", "CUES_SESSION_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Configure root .env: " + ", ".join(required))
    rows = get_client().table("activities").select(",".join(Activity.model_fields)).execute().data
    activities = [Activity.model_validate(row) for row in rows]
    if not activities:
        raise SystemExit("Supabase activities catalog is empty")
    model = ChatGroq(model="openai/gpt-oss-20b", timeout=20, max_retries=2)
    create_seat_state_runtime(model, activities).run_forever()


if __name__ == "__main__":
    main()
