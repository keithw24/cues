"""Access to the LOCAL Supabase stack (`supabase start`) for contract and smoke tests.

Only ever talks to 127.0.0.1. Reads the stack's URL and keys from `supabase status`, so no
credential is stored or printed, and runs SQL inside the database container with psql.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

DB_CONTAINER = "supabase_db_cues"  # supabase/config.toml project_id = "cues"


@dataclass(frozen=True)
class Stack:
    api_url: str
    secret_key: str
    publishable_key: str


@lru_cache(maxsize=1)
def stack() -> Stack | None:
    """The running local stack, or None when Docker / the CLI / the stack is not available."""
    if not shutil.which("supabase") or not shutil.which("docker"):
        return None
    try:
        status = subprocess.run(
            ["supabase", "status", "-o", "json"], capture_output=True, text=True, timeout=30
        )
        found = json.loads(status.stdout)
        result = Stack(found["API_URL"], found["SECRET_KEY"], found["PUBLISHABLE_KEY"])
    except Exception:
        return None
    return result if result.api_url.startswith("http://127.0.0.1") else None


def sql(statement: str) -> list[dict]:
    """Run one SELECT-like statement as the database owner; returns its rows as dicts."""
    wrapped = f"select coalesce(json_agg(t), '[]'::json) from ({statement}) t"
    out = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", "postgres", "-At", "-c", wrapped],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)


def execute(statement: str) -> None:
    out = subprocess.run(
        [
            "docker",
            "exec",
            DB_CONTAINER,
            "psql",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode:
        raise RuntimeError(out.stderr.strip())


def http(method: str, path: str, body=None, *, key: str, token: str | None = None):
    """Call the local API (auth, PostgREST, RPC). Returns (status, parsed JSON or text)."""
    s = stack()
    assert s is not None
    request = urllib.request.Request(
        s.api_url + path,
        None if body is None else json.dumps(body).encode(),
        {
            "apikey": key,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token or key}",
            "Prefer": "return=representation",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
            return response.status, (json.loads(data) if data else None)
    except urllib.error.HTTPError as error:
        text = error.read().decode()
        try:
            return error.code, json.loads(text)
        except ValueError:
            return error.code, text
