from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
    assert review.resolved_at is None
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


@pytest.mark.parametrize(
    ("operation", "status"),
    [("confirm_needs_attention", "confirmed"), ("dismiss_review", "dismissed")],
)
def test_teacher_resolution_preserves_context_and_assessment(operation, status):
    resolved_at = NOW + timedelta(seconds=30)
    times = iter([NOW, resolved_at])
    store = TeacherReviewStore(clock=lambda: next(times))
    original = store.request_teacher_review(request(), assessment())
    resolved = getattr(store, operation)(original.id)

    assert resolved.status == status
    assert resolved.resolved_at == resolved_at
    assert resolved.id == original.id
    assert resolved.created_at == original.created_at
    assert resolved.evaluation == original.evaluation
    assert resolved.assessment == original.assessment
    assert store.get_pending_reviews() == []
    assert store.get_review(original.id) == resolved
    assert TeacherReview.model_validate_json(resolved.model_dump_json()) == resolved
    assert original.status == "pending" and original.resolved_at is None


@pytest.mark.parametrize("operation", ["get_review", "confirm_needs_attention", "dismiss_review"])
def test_unknown_review_id_fails_without_mutating_store(operation):
    store = TeacherReviewStore(clock=lambda: NOW)
    original = store.request_teacher_review(request(), assessment())
    with pytest.raises(KeyError, match="unknown review ID"):
        getattr(store, operation)(UUID(int=0))
    assert store.get_pending_reviews() == [original]


@pytest.mark.parametrize("first", ["confirm_needs_attention", "dismiss_review"])
@pytest.mark.parametrize("second", ["confirm_needs_attention", "dismiss_review"])
def test_resolved_review_rejects_same_or_opposite_transition(first, second):
    # A third clock access would fail: rejected transitions cannot reset time.
    times = iter([NOW, NOW + timedelta(seconds=5)])
    store = TeacherReviewStore(clock=lambda: next(times))
    original = store.request_teacher_review(request(), assessment())
    resolved = getattr(store, first)(original.id)
    with pytest.raises(ValueError, match="already resolved"):
        getattr(store, second)(original.id)
    assert store.get_review(original.id) == resolved
    assert store.get_pending_reviews() == []


def test_pending_retrieval_filters_resolved_and_preserves_order():
    store = TeacherReviewStore(clock=lambda: NOW)
    reviews = [
        store.request_teacher_review(replace(request(), seat_id=seat), assessment())
        for seat in ["A", "B", "C", "D"]
    ]
    store.confirm_needs_attention(reviews[0].id)
    store.dismiss_review(reviews[2].id)
    assert store.get_pending_reviews() == [reviews[1], reviews[3]]


def test_resolved_review_copies_do_not_mutate_stored_evidence():
    store = TeacherReviewStore(clock=lambda: NOW)
    original = store.request_teacher_review(request(), assessment())
    resolved = store.confirm_needs_attention(original.id)
    resolved.assessment.evidence_used.clear()
    fetched = store.get_review(original.id)
    assert fetched.assessment.evidence_used == ["current_progress"]
    fetched.assessment.evidence_used.clear()
    assert store.get_review(original.id).assessment.evidence_used == ["current_progress"]


@pytest.mark.parametrize("operation", ["confirm_needs_attention", "dismiss_review"])
def test_agent_request_cannot_reopen_resolved_review_or_reclaim_capacity(operation):
    store = TeacherReviewStore(capacity=1, clock=lambda: NOW)
    original = store.request_teacher_review(request(), assessment())
    resolved = getattr(store, operation)(original.id)
    with pytest.raises(ValueError, match="already resolved"):
        store.request_teacher_review(request(), assessment())
    with pytest.raises(ValueError, match="capacity"):
        store.request_teacher_review(replace(request(), seat_id="B"), assessment())
    assert store.get_review(original.id) == resolved
    assert store.get_pending_reviews() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "pending", "resolved_at": NOW},
        {"status": "confirmed"},
        {"status": "dismissed"},
        {"status": "confirmed", "resolved_at": NOW - timedelta(seconds=1)},
        {"status": "dismissed", "resolved_at": "2026-11-14T00:00:01"},
    ],
)
def test_resolution_schema_rejects_inconsistent_or_invalid_timestamps(changes):
    store = TeacherReviewStore(clock=lambda: NOW)
    review = store.request_teacher_review(request(), assessment())
    with pytest.raises(ValidationError):
        TeacherReview.model_validate(review.model_dump() | changes)


def test_invalid_resolution_clock_leaves_review_pending():
    times = iter([NOW, NOW - timedelta(seconds=1)])
    store = TeacherReviewStore(clock=lambda: next(times))
    review = store.request_teacher_review(request(), assessment())
    with pytest.raises(ValidationError, match="cannot precede"):
        store.confirm_needs_attention(review.id)
    assert store.get_review(review.id) == review
    assert store.get_pending_reviews() == [review]


def test_one_open_review_per_person_in_the_local_store():
    from datetime import timedelta

    store = TeacherReviewStore()
    first = store.request_teacher_review(request(), assessment())
    again = store.request_teacher_review(
        replace(request(), observed_at=NOW + timedelta(seconds=30)), assessment()
    )
    assert again.id == first.id and len(store.get_pending_reviews()) == 1
    assert (
        store.request_teacher_review(replace(request(), seat_id="B"), assessment()).id != first.id
    )
    store.dismiss_review(first.id)
    reopened = store.request_teacher_review(
        replace(request(), observed_at=NOW + timedelta(seconds=60)), assessment()
    )
    assert reopened.id != first.id
