"""Supabase connection for the vision service.

Reads SUPABASE_URL and SUPABASE_KEY from the environment (or vision/.env).
Returns None when they are not set, so the service still runs offline.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


@lru_cache(maxsize=1)
def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)
