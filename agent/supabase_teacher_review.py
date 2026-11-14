"""Explicitly injected server-side persistence; no environment-triggered writes."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from httpx import HTTPError
from postgrest.exceptions import APIError
from pydantic import TypeAdapter

from agent.assessment import AgentAssessment
from agent.router import AgentEvaluationRequest
from agent.teacher_review import TeacherReview, validate_review_request
from supabase import Client


class TeacherReviewPersistenceError(RuntimeError):
    """A database/network failure, never an empty history or successful write."""


def _evaluation_json(evaluation: AgentEvaluationRequest) -> dict:
    if evaluation.observed_at.utcoffset() is None:
        raise ValueError("evaluation observed_at must be timezone-aware")
    data = TypeAdapter(AgentEvaluationRequest).dump_python(evaluation, mode="json")
    # Datetime equality treats equivalent timezone offsets as the same instant.
    # Use one representation for the database's cross-process uniqueness check.
    data["observed_at"] = evaluation.observed_at.astimezone(UTC).isoformat()
    return data


def review_to_row(review: TeacherReview) -> dict:
    """Flatten dashboard fields while retaining the complete trusted evaluation."""
    review = TeacherReview.model_validate(review.model_dump())
    data = review.model_dump(mode="json")
    evaluation = _evaluation_json(review.evaluation)
    return {
        "id": data["id"],
        "created_at": data["created_at"],
        "evaluation": evaluation,
        "session_id": evaluation["session_id"],
        "seat_id": evaluation["seat_id"],
        "activity_id": evaluation["activity_id"],
        "priority": evaluation["escalation"]["priority"],
        "decision": review.assessment.decision,
        "rationale": review.assessment.rationale,
        "evidence_used": list(review.assessment.evidence_used),
        "status": review.status,
        "resolved_at": data["resolved_at"],
    }


def review_from_row(row: dict) -> TeacherReview:
    """Reconstruct canonical typed evidence, checking flattened context consistency."""
    review = TeacherReview.model_validate(
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "evaluation": row["evaluation"],
            "assessment": {key: row[key] for key in ("decision", "rationale", "evidence_used")},
            "status": row["status"],
            "resolved_at": row["resolved_at"],
        }
    )
    expected = review_to_row(review)
    for key in ("session_id", "seat_id", "activity_id", "priority"):
        if row[key] != expected[key]:
            raise ValueError(f"review row has inconsistent {key}")
    validate_review_request(review.evaluation, review.assessment)
    return review


class SupabaseTeacherReviewStore:
    """Same lifecycle API as TeacherReviewStore; Supabase is the source of truth.

    Inject a service-role client on the backend. No fallback to memory on error,
    no automatic migrations, and no global client/environment state.
    """

    def __init__(self, client: Client, *, clock: Callable[[], datetime] | None = None):
        self.client = client
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _execute(query) -> list[dict]:
        try:
            data = query.execute().data
        except (APIError, HTTPError):
            raise TeacherReviewPersistenceError(
                "Supabase teacher-review operation failed"
            ) from None
        if not isinstance(data, list):
            raise TeacherReviewPersistenceError("Supabase returned no review representation")
        return data

    @staticmethod
    def _decode(row: dict) -> TeacherReview:
        try:
            return review_from_row(row)
        except (KeyError, TypeError, ValueError):
            raise TeacherReviewPersistenceError("Supabase returned invalid review data") from None

    def request_teacher_review(
        self, evaluation: AgentEvaluationRequest, assessment: AgentAssessment
    ) -> TeacherReview:
        assessment = validate_review_request(evaluation, assessment)
        review = TeacherReview(
            id=uuid4(), created_at=self._clock(), evaluation=evaluation, assessment=assessment
        )
        row = review_to_row(review)
        rows = self._execute(
            self.client.table("teacher_reviews").upsert(
                row, on_conflict="evaluation", ignore_duplicates=True
            )
        )
        if not rows:
            rows = self._execute(
                self.client.table("teacher_reviews")
                .select("*")
                .eq("evaluation", json.dumps(row["evaluation"]))
                .limit(1)
            )
        if not rows:
            raise TeacherReviewPersistenceError("Stored review could not be retrieved")
        stored = self._decode(rows[0])
        if stored.status != "pending":
            raise ValueError("review already resolved")
        return stored

    def get_review(self, review_id: UUID) -> TeacherReview:
        rows = self._execute(
            self.client.table("teacher_reviews").select("*").eq("id", str(review_id)).limit(1)
        )
        if not rows:
            raise KeyError(f"unknown review ID: {review_id}")
        return self._decode(rows[0])

    def get_pending_reviews(self) -> list[TeacherReview]:
        reviews = []
        # Page explicitly rather than silently truncating at PostgREST's row cap.
        while True:
            rows = self._execute(
                self.client.table("teacher_reviews")
                .select("*")
                .eq("status", "pending")
                .order("created_at")
                .order("id")
                .range(len(reviews), len(reviews) + 199)
            )
            if not rows:
                return reviews
            reviews.extend(self._decode(row) for row in rows)

    def _resolve_review(
        self, review_id: UUID, status: Literal["confirmed", "dismissed"]
    ) -> TeacherReview:
        review = self.get_review(review_id)
        if review.status != "pending":
            raise ValueError("review already resolved")
        resolved = TeacherReview.model_validate(
            {**review.model_dump(), "status": status, "resolved_at": self._clock()}
        )
        rows = self._execute(
            self.client.table("teacher_reviews")
            .update({"status": status, "resolved_at": resolved.resolved_at.isoformat()})
            .eq("id", str(review_id))
            .eq("status", "pending")
        )
        if not rows:
            # Another teacher/process may have resolved it after the first read.
            current = self.get_review(review_id)  # KeyError if the row disappeared.
            if current.status != "pending":
                raise ValueError("review already resolved")
            raise TeacherReviewPersistenceError("Pending review update returned no row")
        return self._decode(rows[0])

    def confirm_needs_attention(self, review_id: UUID) -> TeacherReview:
        return self._resolve_review(review_id, "confirmed")

    def dismiss_review(self, review_id: UUID) -> TeacherReview:
        return self._resolve_review(review_id, "dismissed")
