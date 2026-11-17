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


def function_source(name: str) -> str:
    """The body of a public function (every overload), as the database stores it."""
    rows = sql(
        "select prosrc from pg_proc "
        f"where pronamespace = 'public'::regnamespace and proname = '{name}'"
    )
    assert rows, f"the database has no function {name!r}"
    return "\n".join(row["prosrc"] for row in rows)


def may_execute(role: str, name: str) -> list[bool]:
    """Whether `role` may run each overload of the public function `name`."""
    rows = sql(
        f"select has_function_privilege('{role}', p.oid, 'execute') as ok from pg_proc p "
        f"where p.pronamespace = 'public'::regnamespace and p.proname = '{name}'"
    )
    assert rows, f"the database has no function {name!r}"
    return [row["ok"] for row in rows]


def insert_and_roll_back(table: str, rows: list[dict]) -> None:
    """Insert rows exactly as a producer sends them, then undo it all.

    Every column check, trigger and guard of the real table runs; nothing is left behind.
    Raises RuntimeError with the database's own message when a row is refused.
    """
    statements = ["begin"]
    for row in rows:
        columns = ", ".join(row)
        literal = json.dumps(row).replace("'", "''")
        statements.append(
            f"insert into public.{table} ({columns}) select {columns} "
            f"from jsonb_populate_record(null::public.{table}, '{literal}'::jsonb)"
        )
    statements.append("rollback")
    execute("; ".join(statements))


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
