"""Pending reviews only: no notification, approval, or instructional action."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict

from agent.assessment import AgentAssessment
from agent.router import AgentEvaluationRequest


class TeacherReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    created_at: AwareDatetime
    evaluation: AgentEvaluationRequest
    assessment: AgentAssessment
    status: Literal["pending"] = "pending"


class TeacherReviewStore:
    """Bounded local pending reviews, idempotent per complete evaluation request.

    The first successful action wins for the same request, including across runs.
    Full stores reject new reviews rather than silently evicting pending work.
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
        assessment = AgentAssessment.model_validate(assessment.model_dump())
        if assessment.decision != "teacher_review_warranted":
            raise ValueError("review action requires a teacher-review assessment")
        if (
            not evaluation.escalation.should_evaluate
            or evaluation.escalation.priority is None
            or evaluation.progress.trend != "stalled"
        ):
            raise ValueError("review requires an eligible stalled evaluation")
        with self._lock:
            if evaluation in self._reviews:
                return self._reviews[evaluation].model_copy(deep=True)
            if len(self._reviews) >= self.capacity:
                raise ValueError("pending review capacity reached")
            review = TeacherReview(
                id=uuid4(), created_at=self._clock(), evaluation=evaluation, assessment=assessment
            )
            self._reviews[evaluation] = review
            return review.model_copy(deep=True)

    def get_pending_reviews(self) -> list[TeacherReview]:
        """Return all bounded pending reviews in creation order for future UI use."""
        with self._lock:
            return [review.model_copy(deep=True) for review in self._reviews.values()]
