"""Continuously connect Supabase SeatState snapshots to the existing pipeline."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from agent.context_enricher import ContextEnricher
from agent.deep_agent import AgentRunResult, CuesDeepAgent
from agent.escalation import (
    DEFAULT_ESCALATION_CONFIG,
    EscalationConfig,
    EscalationDecision,
    evaluate_escalation,
)
from agent.progress import ProgressEvaluator, ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.router import AgentEvaluationRequest, EvaluationRouter
from shared.contracts import Activity, SeatState

log = logging.getLogger(__name__)


class SeatStateSource(Protocol):
    """Read the latest row for each seat; implementations do not make decisions."""

    def fetch(self) -> Sequence[Mapping[str, Any] | SeatState]: ...


class SupabaseSeatStateSource:
    """Poll current SeatState rows through the existing backend Supabase client."""

    FIELDS = (
        "seat_id,session_id,activity_id,status,updated_at,tracking_valid,"
        "task_score,expression_context"
    )

    def __init__(self, client) -> None:
        self.client = client

    def fetch(self) -> Sequence[Mapping[str, Any]]:
        response = self.client.table("seat_state").select(self.FIELDS).execute()
        return response.data or []


@dataclass(frozen=True)
class SeatStateProcessingResult:
    snapshot: SeatState
    progress: ProgressState
    escalation: EscalationDecision
    request: AgentEvaluationRequest | None = None
    agent_result: AgentRunResult | None = None


class SeatStatePipeline:
    """Coordinate existing nodes without adding routing or assessment policy."""

    def __init__(
        self,
        activities: Iterable[Activity],
        agent: CuesDeepAgent,
        history: ProgressHistoryStore,
        *,
        router: EvaluationRouter | None = None,
        progress_window_seconds: float = 4,
        escalation_config: EscalationConfig = DEFAULT_ESCALATION_CONFIG,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        catalog = [Activity.model_validate(item.model_dump()) for item in activities]
        self.activities = {item.id: item for item in catalog}
        if len(self.activities) != len(catalog):
            raise ValueError("activity IDs must be unique")
        self.agent = agent
        self.history = history
        self.router = router if router is not None else EvaluationRouter()
        self.enricher = ContextEnricher(catalog)
        self.progress_window_seconds = progress_window_seconds
        self.escalation_config = escalation_config
        self.clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._evaluators: dict[tuple[UUID, str, str], ProgressEvaluator] = {}
        self._last_rows: dict[str, str] = {}

    def process_row(
        self, row: Mapping[str, Any] | SeatState, *, now: datetime | None = None
    ) -> SeatStateProcessingResult | None:
        """Process one changed row; exact unchanged rows are skipped.

        ProgressEvaluator remains authoritative for duplicate timestamps,
        out-of-order/future/stale observations, tracking gaps, and task identity.
        """
        snapshot = row if isinstance(row, SeatState) else SeatState.model_validate(row)
        snapshot = SeatState.model_validate(snapshot.model_dump())
        fingerprint = snapshot.model_dump_json()
        if self._last_rows.get(snapshot.seat_id) == fingerprint:
            return None
        self._last_rows[snapshot.seat_id] = fingerprint
        if snapshot.activity_id is None or snapshot.activity_id not in self.activities:
            raise KeyError(f"unknown activity ID: {snapshot.activity_id!r}")
        activity = self.activities[snapshot.activity_id]
        key = (snapshot.session_id, snapshot.seat_id, snapshot.activity_id)
        evaluator = self._evaluators.get(key)
        if evaluator is None:
            evaluator = self._evaluators[key] = ProgressEvaluator(
                activity, window_seconds=self.progress_window_seconds
            )
        previous_timestamp = evaluator.last
        progress = evaluator.update(snapshot, now=now if now is not None else self.clock())
        # Record only observations the evaluator accepted as fresh. Its public
        # timestamp is the source of truth, so ignored late/future rows do not
        # become misleading history entries.
        if evaluator.last == snapshot.updated_at and evaluator.last != previous_timestamp:
            self.history.record(snapshot, progress)
        escalation = evaluate_escalation(
            progress, snapshot.expression_context, config=self.escalation_config
        )
        request = self.router.route(snapshot, progress, escalation)
        if request is None:
            return SeatStateProcessingResult(snapshot, progress, escalation)
        context = self.enricher.enrich(request)
        agent_result = self.agent.run(context)
        return SeatStateProcessingResult(snapshot, progress, escalation, request, agent_result)


class SeatStateRuntime:
    """Polling lifecycle with per-row isolation and bounded retry cadence."""

    def __init__(
        self,
        source: SeatStateSource,
        pipeline: SeatStatePipeline,
        *,
        poll_seconds: float = 1.0,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.source = source
        self.pipeline = pipeline
        self.poll_seconds = poll_seconds

    def run_once(self) -> list[SeatStateProcessingResult]:
        rows = self.source.fetch()
        results = []
        for row in rows:
            try:
                result = self.pipeline.process_row(row)
                if result is not None:
                    results.append(result)
            except Exception as error:
                seat = row.seat_id if isinstance(row, SeatState) else row.get("seat_id", "unknown")
                log.error("SeatState processing failed for seat %s: %s", seat, type(error).__name__)
        return results

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop if stop is not None else threading.Event()
        while not stop.is_set():
            try:
                self.run_once()
            except Exception as error:
                log.error("SeatState source read failed: %s", type(error).__name__)
            stop.wait(self.poll_seconds)
