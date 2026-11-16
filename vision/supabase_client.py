"""Supabase connection for the vision service.

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment or the
root .env file (see the root .env.example). Returns None when they are not
set, so the service still runs offline.

The station laptop uses the service-role key. Never send it to the browser.
"""

from dotenv import load_dotenv

from shared.supabase_client import REPO_ROOT, get_client

# Keep vision's existing root-env bootstrap; runtime config remains explicit.
load_dotenv(REPO_ROOT / ".env")


def online() -> bool:
    """True when this laptop has database credentials: it follows the teacher's station and
    session and writes to Supabase. False: offline, everything stays in vision/logs."""
    import os

    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


__all__ = ["REPO_ROOT", "get_client", "online"]
