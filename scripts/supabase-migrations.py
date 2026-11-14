"""Explicit hosted targeting for official CLI history repair/list/dry-run/push.

Loads saved backend database credentials without printing them or exposing them
to browser code. Uses official CLI commands without directly editing the ledger.
"""

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = (
    "20261114000100",
    "20261114000200",
    "20261114000300",
    "20261114000310",
    "20261114000400",
    "20261114000500",
    "20261114000510",
    "20261114000520",
    "20261114000600",
    "20261114000700",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "repair-history", "dry-run", "push"))
    action = parser.parse_args().action
    config = {}
    for path in (ROOT / ".env", ROOT / "web/.env", ROOT / "web/.env.local"):
        config.update({k: v for k, v in dotenv_values(path).items() if v})
    config.update({k: v for k, v in os.environ.items() if v})
    url = config.get("DATABASE_URL") or config.get("POSTGRES_URL")
    api = config.get("SUPABASE_URL") or config.get("NEXT_PUBLIC_SUPABASE_URL")
    if not url or not api:
        raise SystemExit("Saved DATABASE_URL and Supabase project URL are required.")
    parsed = urlsplit(url)
    project = (urlsplit(api).hostname or "").split(".")[0]
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or not project
        or (project not in (parsed.hostname or "") and project not in (parsed.username or ""))
    ):
        raise SystemExit("Database connection does not match configured Supabase project.")
    commands = {
        "list": ["migration", "list"],
        "repair-history": ["migration", "repair", "--status", "applied", *VERSIONS],
        "dry-run": ["db", "push", "--dry-run", "--skip-vault"],
        "push": ["db", "push", "--skip-vault"],
    }
    # Capture CLI diagnostics because errors may repeat the supplied connection URI.
    result = subprocess.run(
        ["npx", "--yes", "supabase@3.1.0", *commands[action], "--remote=" + url, "--yes"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    for secret in (
        url,
        parsed.password,
        unquote(parsed.password or ""),
        config.get("SUPABASE_ACCESS_TOKEN"),
        config.get("SUPABASE_SERVICE_ROLE_KEY"),
    ):
        if secret:
            output = output.replace(secret, "[redacted]")
    print(output, end="")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
