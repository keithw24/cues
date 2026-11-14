"""In-memory episode deduplication, without agent invocation or timed cooldowns."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from shared.contracts import SeatState


@dataclass(frozen=True)
class AgentEvaluationRequest:
    session_id: UUID
    seat_id: str
    activity_id: str
    observed_at: datetime
    progress: ProgressState
    escalation: EscalationDecision


class EvaluationRouter:
    """One instance may route multiple seats. Supply matched, fresh inputs in order.

    Unknown pauses suppression even though ProgressEvaluator resets its timer.
    Improving/completed or explicit reset starts a new episode. This local state
    is not durable, thread-safe, or a delivery/retry guarantee.
    """

    def __init__(self) -> None:
        self._levels: dict[tuple[UUID, str, str], int] = {}

    def reset(self, *, session_id: UUID, seat_id: str, activity_id: str) -> None:
        """Forget a task episode, including when restarting the same activity."""
        self._levels.pop((session_id, seat_id, activity_id), None)

    def route(
        self, snapshot: SeatState, progress: ProgressState, decision: EscalationDecision
    ) -> AgentEvaluationRequest | None:
        """Return a request once per stronger eligible level; otherwise None.

        All three inputs must refer to the same observation. Caller owns freshness
        and ordering. Marking a level means a request was returned, not delivered.
        """
        snapshot = SeatState.model_validate(snapshot.model_dump())
        if snapshot.activity_id is None:
            return None
        key = (snapshot.session_id, snapshot.seat_id, snapshot.activity_id)
        if progress.trend in ("improving", "completed"):
            self._levels.pop(key, None)
            return None
        if (
            progress.trend != "stalled"
            or not decision.should_evaluate
            or snapshot.tracking_valid is not True
            or snapshot.status in ("idle", "tracking_lost", "done")
        ):
            return None
        levels = {
            ("normal", "stalled_progress"): 1,
            ("elevated", "stalled_progress_with_expression_context"): 2,
            ("elevated", "prolonged_stalled_progress"): 3,
        }
        level = levels.get((decision.priority, decision.reason))
        if level is None:
            raise ValueError("eligible decision has an unsupported priority/reason pair")
        if level <= self._levels.get(key, 0):
            return None
        self._levels[key] = level
        return AgentEvaluationRequest(
            session_id=snapshot.session_id,
            seat_id=snapshot.seat_id,
            activity_id=snapshot.activity_id,
            observed_at=snapshot.updated_at,
            progress=progress,
            escalation=decision,
        )
