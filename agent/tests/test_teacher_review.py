from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent.assessment import AgentAssessment
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.router import AgentEvaluationRequest
from agent.teacher_review import TeacherReview, TeacherReviewStore

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def request():
    return AgentEvaluationRequest(
        UUID(int=1),
        "A",
        "task",
        NOW,
        ProgressState("stalled", 10),
        EscalationDecision(True, "normal", "stalled_progress"),
    )


def assessment():
    return AgentAssessment(
        decision="teacher_review_warranted",
        rationale="Review this task progress.",
        evidence_used=["current_progress"],
    )


def test_pending_review_identity_and_schema():
    store = TeacherReviewStore(clock=lambda: NOW)
    review = store.request_teacher_review(request(), assessment())
    assert review.created_at == NOW
    assert review.evaluation.session_id == UUID(int=1)
    assert review.evaluation.seat_id == "A" and review.evaluation.activity_id == "task"
    assert review.evaluation.escalation.priority == "normal"
    assert review.status == "pending"
    assert TeacherReview.model_validate_json(review.model_dump_json()) == review
    with pytest.raises(ValidationError):
        TeacherReview.model_validate(review.model_dump() | {"status": "approved"})
    with pytest.raises(ValidationError):
        TeacherReview.model_validate(review.model_dump() | {"created_at": "2026-11-14T00:00:00"})


def test_bounded_storage_and_idempotence_even_when_full():
    store = TeacherReviewStore(capacity=1)
    first = store.request_teacher_review(request(), assessment())
    assert store.request_teacher_review(request(), assessment()).id == first.id
    with pytest.raises(ValueError, match="capacity"):
        store.request_teacher_review(replace(request(), seat_id="B"), assessment())
    assert len(store.get_pending_reviews()) == 1


def test_unique_ids_and_identity_isolation():
    store = TeacherReviewStore()
    first = store.request_teacher_review(request(), assessment())
    second = store.request_teacher_review(replace(request(), seat_id="B"), assessment())
    assert first.id != second.id
    assert len(store.get_pending_reviews()) == 2


def test_retrieval_detaches_mutable_evidence():
    store = TeacherReviewStore()
    store.request_teacher_review(request(), assessment())
    store.get_pending_reviews()[0].assessment.evidence_used.clear()
    assert store.get_pending_reviews()[0].assessment.evidence_used == ["current_progress"]


def test_no_review_for_monitoring_or_ineligible_input():
    store = TeacherReviewStore()
    with pytest.raises(ValueError):
        store.request_teacher_review(
            request(), assessment().model_copy(update={"decision": "continue_monitoring"})
        )
    with pytest.raises(ValueError):
        store.request_teacher_review(
            replace(request(), progress=ProgressState("completed")), assessment()
        )
    assert store.get_pending_reviews() == []
