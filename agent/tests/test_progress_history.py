from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryEntry, ProgressHistoryStore
from shared.contracts import SeatState


def snapshot(second=0, **changes):
    return SeatState.model_validate(
        dict(
            session_id=UUID(int=1),
            seat_id="A",
            activity_id="task",
            status="in_progress",
            tracking_valid=True,
            updated_at=datetime(2026, 11, 14, tzinfo=UTC) + timedelta(seconds=second),
        )
        | changes
    )


def read(store, **changes):
    return store.get_recent_progress_history(
        **(dict(session_id=UUID(int=1), seat_id="A", activity_id="task", limit=2) | changes)
    )


def test_recent_chronological_typed_and_deterministic():
    store = ProgressHistoryStore()
    for second, trend in [(3, "completed"), (1, "improving"), (2, "stalled")]:
        store.record(snapshot(second), ProgressState(trend, 2 if trend == "stalled" else 0))
    result = read(store)
    assert [e.progress.trend for e in result] == ["stalled", "completed"]
    assert [e.observed_at for e in result] == [snapshot(2).updated_at, snapshot(3).updated_at]
    assert result == read(store)
    assert all(isinstance(e, ProgressHistoryEntry) for e in result)
    assert ProgressHistoryEntry.model_validate_json(result[0].model_dump_json()) == result[0]


def test_capacity_and_late_record_retention():
    store = ProgressHistoryStore(capacity=2)
    for second in [1, 2, 3, 0]:
        store.record(snapshot(second), ProgressState("stalled", second))
    assert [e.progress.stalled_seconds for e in read(store)] == [2, 3]
    assert len(read(store, limit=1)) == 1


def test_empty_history():
    assert read(ProgressHistoryStore()) == []


@pytest.mark.parametrize(
    "change", [{"seat_id": "B"}, {"activity_id": "other"}, {"session_id": UUID(int=2)}]
)
def test_identity_isolation(change):
    store = ProgressHistoryStore()
    store.record(snapshot(), ProgressState("improving"))
    assert read(store, **change) == []
    store.record(snapshot(**change), ProgressState("completed"))
    assert read(store, **change)[0].progress.trend == "completed"
    assert read(store)[0].progress.trend == "improving"


def test_duplicate_timestamp_replaces_summary():
    store = ProgressHistoryStore()
    store.record(snapshot(), ProgressState("unknown"))
    store.record(snapshot(), ProgressState("stalled", 4))
    assert len(read(store)) == 1
    assert read(store)[0].progress.stalled_seconds == 4


@pytest.mark.parametrize("limit", [0, -1, 51, True])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        read(ProgressHistoryStore(), limit=limit)


def test_missing_activity_is_not_invented():
    with pytest.raises(ValueError):
        ProgressHistoryStore().record(snapshot(activity_id=None), ProgressState("unknown"))


def test_default_limit_with_smaller_capacity():
    store = ProgressHistoryStore(capacity=1)
    store.record(snapshot(), ProgressState("completed"))
    assert len(store.get_recent_progress_history(UUID(int=1), "A", "task")) == 1
