"""Shared server-side client factory; never import this from frontend code."""

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=8)
def get_client(url: str | None = None, key: str | None = None):
    """Reuse a backend client; callers can supply explicitly resolved credentials.

    No-argument callers retain the existing optional vision-client behavior.
    Agent runtime validates complete configuration before calling this factory.
    """
    url = url if url is not None else os.environ.get("SUPABASE_URL")
    key = key if key is not None else os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)
