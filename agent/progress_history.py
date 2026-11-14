"""Bounded, explicitly recorded progress summaries for the future agent tool."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from agent.progress import ProgressState
from shared.contracts import SeatState


class ProgressHistoryEntry(BaseModel):
    """An evaluated progress summary, not a raw perception observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: AwareDatetime
    progress: ProgressState


class ProgressHistoryStore:
    """Local history only. Callers explicitly record evaluated task observations.

    Retains at most capacity summaries per session/seat/activity. No automatic
    pipeline wiring or persistence; later this can be backed by Supabase.
    """

    def __init__(self, capacity: int = 50) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 50:
            raise ValueError("capacity must be an integer between 1 and 50")
        self.capacity = capacity
        self._history: dict[tuple[UUID, str, str], list[ProgressHistoryEntry]] = {}

    def record(self, snapshot: SeatState, progress: ProgressState) -> None:
        """Record matched evaluator output; preserve only timestamp and summary.

        Timestamp duplicates replace the prior summary. Late records are sorted
        by observation time and cannot displace more recent retained history.
        """
        snapshot = SeatState.model_validate(snapshot.model_dump())
        if snapshot.activity_id is None:
            raise ValueError("history requires an activity_id")
        entry = ProgressHistoryEntry(observed_at=snapshot.updated_at, progress=progress)
        key = (snapshot.session_id, snapshot.seat_id, snapshot.activity_id)
        entries = [e for e in self._history.get(key, []) if e.observed_at != entry.observed_at]
        entries.append(entry)
        entries.sort(key=lambda e: e.observed_at)
        self._history[key] = entries[-self.capacity :]

    def get_recent_progress_history(
        self, session_id: UUID, seat_id: str, activity_id: str, limit: int = 10
    ) -> list[ProgressHistoryEntry]:
        """Retrieve recent evaluated progress summaries for one session/seat/task.

        Returns up to limit entries in chronological order, each containing
        observed_at and progress (trend and stalled_seconds). Empty means no
        retained matching data, not independent success or absence of difficulty.
        Only recorded summaries are available; no frames, diagnoses, or prompts.
        """
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        key = (UUID(str(session_id)), seat_id, activity_id)
        return [e.model_copy(deep=True) for e in self._history.get(key, [])[-limit:]]
