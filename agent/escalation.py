"""Pure escalation eligibility; no agent calls, alerts, or cooldown state."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from agent.progress import ProgressState
from shared.contracts import ExpressionContext


@dataclass(frozen=True)
class EscalationConfig:
    min_observation_seconds: float = 5
    expression_assisted_seconds: float = 6
    normal_stall_seconds: float = 10
    prolonged_stall_seconds: float = 15
    expression_min_probability: float = 0.5
    expression_min_duration_seconds: float = 5

    def __post_init__(self) -> None:
        times = (
            self.min_observation_seconds,
            self.expression_assisted_seconds,
            self.normal_stall_seconds,
            self.prolonged_stall_seconds,
        )
        if any(not isfinite(t) or t <= 0 for t in times) or not (
            self.min_observation_seconds
            <= self.expression_assisted_seconds
            <= self.prolonged_stall_seconds
            and self.min_observation_seconds
            <= self.normal_stall_seconds
            <= self.prolonged_stall_seconds
        ):
            raise ValueError(
                "timings must be finite, positive, and within minimum/prolonged bounds"
            )
        if (
            not isfinite(self.expression_min_probability)
            or not 0 <= self.expression_min_probability <= 1
        ):
            raise ValueError("expression probability must be within [0, 1]")
        if (
            not isfinite(self.expression_min_duration_seconds)
            or self.expression_min_duration_seconds <= 0
        ):
            raise ValueError("expression persistence must be finite and positive")


DEFAULT_ESCALATION_CONFIG = EscalationConfig()
DEMO_ESCALATION_CONFIG = EscalationConfig(
    min_observation_seconds=2,
    expression_assisted_seconds=5,
    normal_stall_seconds=4,
    prolonged_stall_seconds=6,
)


@dataclass(frozen=True)
class EscalationDecision:
    should_evaluate: bool
    priority: Literal["normal", "elevated"] | None = None
    reason: (
        Literal[
            "stalled_progress",
            "stalled_progress_with_expression_context",
            "prolonged_stalled_progress",
        ]
        | None
    ) = None


def evaluate_escalation(
    progress_state: ProgressState,
    expression_context: ExpressionContext | None = None,
    *,
    config: EscalationConfig = DEFAULT_ESCALATION_CONFIG,
) -> EscalationDecision:
    """Evaluate a fresh ProgressState; caller supplies current expression context.

    stalled_seconds is a conservative lower bound on valid observation time.
    No wall-clock time or expression-only input can advance this timer here.
    A true result requests evaluation, never teacher notification or intervention.
    """
    seconds = progress_state.stalled_seconds
    if not isfinite(seconds) or seconds < 0:
        raise ValueError("stalled_seconds must be finite and nonnegative")
    if progress_state.trend != "stalled" or seconds < config.min_observation_seconds:
        return EscalationDecision(False)
    if seconds >= config.prolonged_stall_seconds:
        return EscalationDecision(True, "elevated", "prolonged_stalled_progress")
    if expression_context is not None:
        context = ExpressionContext.model_validate(expression_context.model_dump())
        qualifying = (
            context.label in ("anger", "fear", "sadness")
            and context.probability >= config.expression_min_probability
            and (context.duration_seconds or 0) >= config.expression_min_duration_seconds
        )
        if qualifying and seconds >= config.expression_assisted_seconds:
            return EscalationDecision(True, "elevated", "stalled_progress_with_expression_context")
    if seconds >= config.normal_stall_seconds:
        return EscalationDecision(True, "normal", "stalled_progress")
    return EscalationDecision(False)
