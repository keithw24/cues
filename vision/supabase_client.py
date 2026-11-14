"""Supabase connection for the vision service.

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment or the
root .env file (see the root .env.example). Returns None when they are not
set, so the service still runs offline.

The station laptop uses the service-role key. Never send it to the browser.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")


@lru_cache(maxsize=1)
def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)
