"""Find (and optionally delete) stale seat_state rows: old layouts and finished test runs.

seat_state keeps one latest row per person id. Rows from earlier layouts (S1-L, S1-R) and from
sessions that ended long ago just sit there. They are read-only noise for the dashboard (it
shows only fresh people) but they clutter the table and the Supabase views.

A row is stale when it has not been updated for --hours (default 24) AND one of:
  * its id is from the old fixed-seat layout (S1-L, S1-R),
  * its session has ended,
  * its session no longer exists (or it never had one).

    uv run python scripts/cleanup-seat-state.py            # dry run: lists what would go
    uv run python scripts/cleanup-seat-state.py --delete   # asks, then deletes those rows

Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the root .env (never printed). Only
seat_state is touched. Live people (updated recently, in a running session) are never listed.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SEAT = re.compile(r"^[A-Za-z0-9]+-[LR]$")


def parse_time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def stale_reason(row: dict, sessions: dict[str, dict], now: datetime, hours: float) -> str | None:
    """Why this row is stale, or None to keep it. Pure: no database access."""
    updated = parse_time(row.get("updated_at"))
    if updated is not None and now - updated < timedelta(hours=hours):
        return None  # updated recently: never touch it, whatever the layout
    if LEGACY_SEAT.match(str(row.get("seat_id", ""))):
        return "old fixed-seat layout"
    session_id = row.get("session_id")
    if not session_id:
        return "no session"
    session = sessions.get(str(session_id))
    if session is None:
        return "session no longer exists"
    if session.get("ended_at"):
        return "session ended"
    # A still-running session with an old row (the person left): keep it.
    return None


def find_stale(rows, sessions, now=None, hours=24.0):
    now = now or datetime.now(UTC)
    found = []
    for row in rows:
        reason = stale_reason(row, sessions, now, hours)
        if reason:
            found.append((row["seat_id"], reason))
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hours", type=float, default=24.0, help="minimum age (default 24)")
    parser.add_argument("--delete", action="store_true", help="delete after confirming")
    args = parser.parse_args(argv)
    if args.hours <= 0:
        raise SystemExit("--hours must be positive")

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT))
    from shared.supabase_client import get_client

    client = get_client()
    if client is None:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the root .env.")
    rows = client.table("seat_state").select("seat_id,session_id,updated_at").execute().data or []
    ids = sorted({str(r["session_id"]) for r in rows if r.get("session_id")})
    sessions: dict[str, dict] = {}
    if ids:
        read = client.table("sessions").select("id,ended_at").in_("id", ids).execute().data or []
        sessions = {str(s["id"]): s for s in read}
    stale = find_stale(rows, sessions, hours=args.hours)
    print(f"{len(rows)} seat_state rows; {len(stale)} stale (not updated for {args.hours:g}h+).")
    for seat_id, reason in stale:
        print(f"  {seat_id}: {reason}")
    if not stale:
        return 0
    if not args.delete:
        print("Dry run: nothing deleted. Add --delete to remove these rows.")
        return 0
    if (
        input(f"Delete {len(stale)} seat_state rows? Type 'delete' to confirm: ").strip()
        != "delete"
    ):
        print("Cancelled; nothing deleted.")
        return 1
    for seat_id, _ in stale:
        client.table("seat_state").delete().eq("seat_id", seat_id).execute()
    print(f"Deleted {len(stale)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
