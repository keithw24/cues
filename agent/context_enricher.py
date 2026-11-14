"""Resolve task context locally without making routing or agent decisions."""

from collections.abc import Iterable
from dataclasses import dataclass

from agent.router import AgentEvaluationRequest
from shared.contracts import Activity


@dataclass(frozen=True)
class EnrichedEvaluationContext:
    request: AgentEvaluationRequest
    activity: Activity


class ContextEnricher:
    """An explicit snapshot of known activities, supplied by the caller.

    No fixture reads or service calls happen here. Construct a new enricher when
    the activity catalog changes. Unknown IDs raise KeyError instead of guessing.
    """

    def __init__(self, activities: Iterable[Activity]) -> None:
        self._activities: dict[str, Activity] = {}
        for activity in activities:
            validated = Activity.model_validate(activity.model_dump())
            if validated.id in self._activities:
                raise ValueError(f"duplicate activity id: {validated.id}")
            self._activities[validated.id] = validated

    def enrich(self, request: AgentEvaluationRequest) -> EnrichedEvaluationContext:
        """Attach the matching activity; preserve all existing request context."""
        activity = self._activities[request.activity_id]
        # Activity is mutable; callers must not mutate the stored catalog through
        # an enriched result, or leak changes into another request.
        return EnrichedEvaluationContext(request, activity.model_copy(deep=True))
