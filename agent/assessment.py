"""Internal structured assessment shared by agent and review storage."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.contracts import InterventionKey


class AgentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["continue_monitoring", "teacher_review_warranted"]
    rationale: str = Field(min_length=1, max_length=500, pattern=r"\S")
    evidence_used: list[
        Literal["current_progress", "activity", "recent_progress_history", "prompt_history"]
    ] = Field(min_length=1, max_length=4)
    # One item from the approved menu, or None. A suggestion only: the teacher approves.
    suggested_intervention: InterventionKey | None = None

    @field_validator("evidence_used")
    @classmethod
    def unique_evidence(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("evidence labels must be unique")
        return value
