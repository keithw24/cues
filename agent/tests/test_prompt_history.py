from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent.prompt_history import PromptHistoryEntry, PromptHistoryStore

KEY = (UUID(int=1), "A", "raise_hand")


def entry(second=0, outcome="independent_correct"):
    return PromptHistoryEntry(
        observed_at=datetime(2026, 11, 14, tzinfo=UTC) + timedelta(seconds=second), outcome=outcome
    )


def test_record_order_and_typed_determinism():
    store = PromptHistoryStore()
    for second, outcome in [(2, "prompted_correct"), (0, "incorrect"), (1, "no_response")]:
        store.record(*KEY, entry(second, outcome))
    result = store.get_prompt_history(*KEY)
    assert [e.outcome for e in result] == ["incorrect", "no_response", "prompted_correct"]
    assert result == store.get_prompt_history(*KEY)
    assert all(isinstance(e, PromptHistoryEntry) for e in result)
    assert PromptHistoryEntry.model_validate_json(result[0].model_dump_json()) == result[0]
    assert set(result[0].model_dump()) == {"observed_at", "outcome"}


def test_retention_retrieval_bounds_and_late_record():
    store = PromptHistoryStore(capacity=3)
    for second in range(6):
        store.record(*KEY, entry(second))
    store.record(*KEY, entry(-1))
    assert store.get_prompt_history(*KEY) == [entry(3), entry(4), entry(5)]
    assert store.get_prompt_history(*KEY, limit=2) == [entry(4), entry(5)]


def test_default_retrieval_bound():
    store = PromptHistoryStore()
    for second in range(20):
        store.record(*KEY, entry(second))
    assert len(store.get_prompt_history(*KEY)) == 10


def test_empty_history():
    assert PromptHistoryStore().get_prompt_history(*KEY) == []


@pytest.mark.parametrize(
    "other",
    [
        (UUID(int=1), "B", "raise_hand"),
        (UUID(int=2), "A", "raise_hand"),
        (UUID(int=1), "A", "other"),
    ],
)
def test_identity_isolation(other):
    store = PromptHistoryStore()
    store.record(*KEY, entry())
    assert store.get_prompt_history(*other) == []
    store.record(*other, entry(1, "prompted_correct"))
    assert store.get_prompt_history(*KEY) == [entry()]
    assert store.get_prompt_history(*other) == [entry(1, "prompted_correct")]


def test_global_storage_bound_does_not_evict_existing_identity():
    store = PromptHistoryStore(max_keys=1)
    store.record(*KEY, entry())
    with pytest.raises(ValueError, match="identity capacity"):
        store.record(UUID(int=2), "A", "raise_hand", entry())
    store.record(*KEY, entry(1))
    assert len(store.get_prompt_history(*KEY)) == 2


@pytest.mark.parametrize(
    "changes",
    [{"outcome": "frustrated"}, {"observed_at": "2026-11-14T00:00:00"}, {"prompt_level": "verbal"}],
)
def test_record_schema_rejects_unsupported_values(changes):
    with pytest.raises(ValidationError):
        PromptHistoryEntry.model_validate(entry().model_dump() | changes)


@pytest.mark.parametrize("limit", [0, 11, True])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        PromptHistoryStore().get_prompt_history(*KEY, limit=limit)


@pytest.mark.parametrize("kwargs", [{"capacity": 0}, {"capacity": 51}, {"max_keys": 0}])
def test_invalid_storage_configuration(kwargs):
    with pytest.raises(ValueError):
        PromptHistoryStore(**kwargs)


def test_invalid_identity_rejected():
    with pytest.raises(ValidationError):
        PromptHistoryStore().record(UUID(int=1), " ", "raise_hand", entry())


def test_equal_timestamps_preserve_observation_order():
    store = PromptHistoryStore()
    store.record(*KEY, entry(0, "incorrect"))
    store.record(*KEY, entry(0, "prompted_correct"))
    assert [e.outcome for e in store.get_prompt_history(*KEY)] == ["incorrect", "prompted_correct"]
