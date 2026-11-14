"""Explicit observable prompt outcomes; no inference or agent registration."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, TypeAdapter

from shared.contracts import Identifier

_KEY = TypeAdapter(tuple[UUID, Identifier, Identifier])


class PromptHistoryEntry(BaseModel):
    """A manually/synthetically supplied observed response, not a CV inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: AwareDatetime
    outcome: Literal["independent_correct", "prompted_correct", "incorrect", "no_response"]


class PromptHistoryStore:
    """Small local store; an observation producer is not yet implemented.

    Retains the newest capacity records per identity. New identities beyond
    max_keys are rejected rather than silently evicting another learner's data.
    Equal timestamps preserve insertion order. Repeated records are not deduped.
    """

    def __init__(self, capacity: int = 50, max_keys: int = 100) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 50:
            raise ValueError("capacity must be an integer between 1 and 50")
        if type(max_keys) is not int or not 1 <= max_keys <= 1000:
            raise ValueError("max_keys must be an integer between 1 and 1000")
        self.capacity = capacity
        self.max_keys = max_keys
        self._history: dict[tuple[UUID, str, str], list[PromptHistoryEntry]] = {}

    def record(
        self, session_id: UUID, seat_id: str, activity_id: str, entry: PromptHistoryEntry
    ) -> None:
        """Record an explicitly observed outcome for exactly one task identity.

        Caller must know independence/correctness from an actual observation;
        never derive these categories from emotion, tracking loss, or a stall.
        """
        key = _KEY.validate_python((session_id, seat_id, activity_id))
        validated = PromptHistoryEntry.model_validate(entry.model_dump())
        if key not in self._history and len(self._history) >= self.max_keys:
            raise ValueError("prompt history identity capacity reached")
        entries = [*self._history.get(key, []), validated]
        entries.sort(key=lambda e: e.observed_at)
        self._history[key] = entries[-self.capacity :]

    def get_prompt_history(
        self, session_id: UUID, seat_id: str, activity_id: str, limit: int = 10
    ) -> list[PromptHistoryEntry]:
        """Return recent observed response outcomes for this session/seat/activity.

        Entries are chronological, each with observed_at and outcome. Empty means
        no retained matching observations, not failure, independence, or need for
        support. This information tool does not recommend or change instruction.
        """
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("limit must be an integer between 1 and 10")
        key = _KEY.validate_python((session_id, seat_id, activity_id))
        return [e.model_copy(deep=True) for e in self._history.get(key, [])[-limit:]]
