"""Shared server-side client factory; never import this from frontend code."""

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUEST_TIMEOUT = 8.0  # seconds, per database request


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
    from supabase import ClientOptions, create_client

    # A request that hangs must fail fast: the library default is 2 minutes, long enough to
    # stall a writer thread and every poll behind it. Callers handle the error and retry.
    return create_client(url, key, options=ClientOptions(postgrest_client_timeout=REQUEST_TIMEOUT))
