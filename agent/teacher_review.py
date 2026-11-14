"""Local review lifecycle: human decisions, no notification or instruction changes."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Literal, Protocol, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from agent.assessment import AgentAssessment
from agent.router import AgentEvaluationRequest


class TeacherReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    created_at: AwareDatetime
    evaluation: AgentEvaluationRequest
    assessment: AgentAssessment
    status: Literal["pending", "confirmed", "dismissed"] = "pending"
    resolved_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if (self.status == "pending") != (self.resolved_at is None):
            raise ValueError("only resolved reviews require resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("resolved_at cannot precede created_at")
        return self


class TeacherReviewStorage(Protocol):
    """The existing lifecycle API, implemented by local and persistent stores."""

    def request_teacher_review(
        self, evaluation: AgentEvaluationRequest, assessment: AgentAssessment
    ) -> TeacherReview: ...

    def get_pending_reviews(self) -> list[TeacherReview]: ...

    def get_review(self, review_id: UUID) -> TeacherReview: ...

    def confirm_needs_attention(self, review_id: UUID) -> TeacherReview: ...

    def dismiss_review(self, review_id: UUID) -> TeacherReview: ...


def validate_review_request(
    evaluation: AgentEvaluationRequest, assessment: AgentAssessment
) -> AgentAssessment:
    """Shared creation checks, independent of where a review is stored."""
    assessment = AgentAssessment.model_validate(assessment.model_dump())
    if assessment.decision != "teacher_review_warranted":
        raise ValueError("review action requires a teacher-review assessment")
    if (
        not evaluation.escalation.should_evaluate
        or evaluation.escalation.priority is None
        or evaluation.progress.trend != "stalled"
    ):
        raise ValueError("review requires an eligible stalled evaluation")
    return assessment


class TeacherReviewStore:
    """Bounded local reviews, with teacher-only resolution operations.

    Duplicate pending requests reuse the first review; resolved requests cannot
    reopen it. Capacity includes resolved reviews, preserving their decisions.
    Full stores reject new reviews rather than silently evicting review history.
    """

    def __init__(self, capacity: int = 100, *, clock: Callable[[], datetime] | None = None):
        if type(capacity) is not int or not 1 <= capacity <= 1000:
            raise ValueError("capacity must be an integer between 1 and 1000")
        self.capacity = capacity
        self._clock = clock or (lambda: datetime.now(UTC))
        self._reviews: dict[AgentEvaluationRequest, TeacherReview] = {}
        self._lock = Lock()

    def request_teacher_review(
        self, evaluation: AgentEvaluationRequest, assessment: AgentAssessment
    ) -> TeacherReview:
        """Create a pending review using trusted evaluation identity and priority."""
        assessment = validate_review_request(evaluation, assessment)
        with self._lock:
            if evaluation in self._reviews:
                existing = self._reviews[evaluation]
                if existing.status != "pending":
                    raise ValueError("review already resolved")
                return existing.model_copy(deep=True)
            if len(self._reviews) >= self.capacity:
                raise ValueError("review capacity reached")
            review = TeacherReview(
                id=uuid4(), created_at=self._clock(), evaluation=evaluation, assessment=assessment
            )
            self._reviews[evaluation] = review
            return review.model_copy(deep=True)

    def get_pending_reviews(self) -> list[TeacherReview]:
        """Return only unresolved reviews in creation order, as detached copies."""
        with self._lock:
            return [
                review.model_copy(deep=True)
                for review in self._reviews.values()
                if review.status == "pending"
            ]

    def _find_review(self, review_id: UUID) -> TeacherReview:
        """Look up a review while the caller holds the store lock."""
        for review in self._reviews.values():
            if review.id == review_id:
                return review
        raise KeyError(f"unknown review ID: {review_id}")

    def get_review(self, review_id: UUID) -> TeacherReview:
        """Look up a pending or resolved review; unknown IDs raise KeyError."""
        with self._lock:
            return self._find_review(review_id).model_copy(deep=True)

    def _resolve_review(
        self, review_id: UUID, status: Literal["confirmed", "dismissed"]
    ) -> TeacherReview:
        with self._lock:
            review = self._find_review(review_id)
            if review.status != "pending":
                raise ValueError("review already resolved")
            resolved = TeacherReview.model_validate(
                {**review.model_dump(), "status": status, "resolved_at": self._clock()}
            )
            self._reviews[review.evaluation] = resolved
            return resolved.model_copy(deep=True)

    def confirm_needs_attention(self, review_id: UUID) -> TeacherReview:
        """Record the teacher's Needs attention choice, without choosing support."""
        return self._resolve_review(review_id, "confirmed")

    def dismiss_review(self, review_id: UUID) -> TeacherReview:
        """Record the teacher's Dismiss choice, without changing instruction."""
        return self._resolve_review(review_id, "dismissed")
