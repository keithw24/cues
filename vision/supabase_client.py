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

__all__ = ["REPO_ROOT", "get_client"]
