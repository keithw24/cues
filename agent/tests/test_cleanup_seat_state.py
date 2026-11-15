"""The stale-row rules of scripts/cleanup-seat-state.py (pure; never touches a database)."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cleanup_seat_state", Path(__file__).resolve().parents[2] / "scripts/cleanup-seat-state.py"
)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
OLD = (NOW - timedelta(days=2)).isoformat()
FRESH = (NOW - timedelta(minutes=5)).isoformat()
SESSIONS = {"ended": {"ended_at": OLD}, "running": {"ended_at": None}}


def reasons(*rows):
    return dict(cleanup.find_stale(list(rows), SESSIONS, now=NOW))


def test_old_layout_rows_go_only_when_old():
    result = reasons(
        {"seat_id": "S1-L", "session_id": "running", "updated_at": OLD},
        {"seat_id": "S2-R", "session_id": None, "updated_at": OLD},
        {"seat_id": "S1-L", "session_id": "running", "updated_at": FRESH},
    )
    assert result == {"S1-L": "old fixed-seat layout", "S2-R": "old fixed-seat layout"}


def test_rows_of_finished_or_missing_sessions_go():
    result = reasons(
        {"seat_id": "S1-P1", "session_id": "ended", "updated_at": OLD},
        {"seat_id": "S1-P2", "session_id": "gone", "updated_at": OLD},
        {"seat_id": "S1-P3", "session_id": None, "updated_at": OLD},
    )
    assert result == {
        "S1-P1": "session ended",
        "S1-P2": "session no longer exists",
        "S1-P3": "no session",
    }


def test_live_people_are_never_listed():
    assert not reasons(
        {"seat_id": "S1-P1", "session_id": "ended", "updated_at": FRESH},  # just updated
        {"seat_id": "S1-P2", "session_id": "running", "updated_at": OLD},  # left a live session
    )


def test_unreadable_times_count_as_old_but_only_with_a_stale_reason():
    assert reasons({"seat_id": "S1-P1", "session_id": "running", "updated_at": "nonsense"}) == {}
    assert reasons({"seat_id": "S1-P1", "session_id": "ended", "updated_at": None}) == {
        "S1-P1": "session ended"
    }
