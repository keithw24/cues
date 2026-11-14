import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from agent.context_enricher import ContextEnricher, EnrichedEvaluationContext
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.router import AgentEvaluationRequest
from shared.contracts import Activity


@pytest.fixture
def activities():
    path = Path(__file__).resolve().parents[2] / "shared/fixtures/activities.json"
    return [Activity.model_validate(row) for row in json.loads(path.read_text())]


def request(activity_id="raise_hand"):
    return AgentEvaluationRequest(
        session_id=UUID(int=1),
        seat_id="S1-L",
        activity_id=activity_id,
        observed_at=datetime(2026, 11, 14, tzinfo=UTC),
        progress=ProgressState("stalled", 10),
        escalation=EscalationDecision(True, "normal", "stalled_progress"),
    )


def test_successful_enrichment(activities):
    original = request()
    result = ContextEnricher(activities).enrich(original)
    assert result.request is original
    assert result.activity == activities[0]
    assert result.activity.name == "Raise your hand"


@pytest.mark.parametrize("catalog", [False, True])
def test_unknown_or_missing_activity_raises(activities, catalog):
    enricher = ContextEnricher(activities if catalog else [])
    with pytest.raises(KeyError, match="unknown"):
        enricher.enrich(request("unknown"))


def test_activity_and_session_isolation(activities):
    enricher = ContextEnricher(activities)
    first = enricher.enrich(request())
    other_request = replace(request("custom_gesture_01"), session_id=UUID(int=2), seat_id="S1-R")
    second = enricher.enrich(other_request)
    assert first.activity.check_type == "rule"
    assert second.activity.check_type == "gesture"
    assert second.activity.success_threshold == 0.78
    assert second.request is other_request
    assert second.activity.id == other_request.activity_id


def test_deterministic_typed_output(activities):
    enricher = ContextEnricher(iter(activities))
    first = enricher.enrich(request())
    second = enricher.enrich(request())
    assert isinstance(first, EnrichedEvaluationContext)
    assert isinstance(first.activity, Activity)
    assert isinstance(first.request, AgentEvaluationRequest)
    assert first == second
    assert first.activity is not second.activity


def test_catalog_is_detached_from_input_and_output_mutation(activities):
    enricher = ContextEnricher(activities)
    activities[0].name = "Changed input"
    first = enricher.enrich(request())
    assert first.activity.name == "Raise your hand"
    first.activity.name = "Changed output"
    assert enricher.enrich(request()).activity.name == "Raise your hand"


def test_duplicate_ids_are_rejected(activities):
    with pytest.raises(ValueError, match="duplicate activity id"):
        ContextEnricher([activities[0], activities[0]])
