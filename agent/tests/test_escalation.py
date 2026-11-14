import pytest

from agent.escalation import (
    DEFAULT_ESCALATION_CONFIG,
    DEMO_ESCALATION_CONFIG,
    EscalationConfig,
    evaluate_escalation,
)
from agent.progress import ProgressState
from shared.contracts import ExpressionContext

CONTEXT = ExpressionContext(label="sadness", probability=0.62, duration_seconds=5)


@pytest.mark.parametrize("config", [DEFAULT_ESCALATION_CONFIG, DEMO_ESCALATION_CONFIG])
@pytest.mark.parametrize("trend", ["improving", "completed", "unknown"])
@pytest.mark.parametrize("context", [None, CONTEXT])
def test_expression_cannot_override_progress_gate(config, trend, context):
    result = evaluate_escalation(ProgressState(trend, 100), context, config=config)
    assert not result.should_evaluate
    assert result.priority is None and result.reason is None


@pytest.mark.parametrize(
    ("config", "seconds", "context", "priority", "reason"),
    [
        (DEFAULT_ESCALATION_CONFIG, 4, CONTEXT, None, None),
        (DEFAULT_ESCALATION_CONFIG, 7, None, None, None),
        (
            DEFAULT_ESCALATION_CONFIG,
            7,
            CONTEXT,
            "elevated",
            "stalled_progress_with_expression_context",
        ),
        (DEFAULT_ESCALATION_CONFIG, 11, None, "normal", "stalled_progress"),
        (DEFAULT_ESCALATION_CONFIG, 16, None, "elevated", "prolonged_stalled_progress"),
        (DEMO_ESCALATION_CONFIG, 1, CONTEXT, None, None),
        (DEMO_ESCALATION_CONFIG, 2, CONTEXT, None, None),
        (
            DEMO_ESCALATION_CONFIG,
            5,
            CONTEXT,
            "elevated",
            "stalled_progress_with_expression_context",
        ),
        (DEMO_ESCALATION_CONFIG, 3, None, None, None),
        (DEMO_ESCALATION_CONFIG, 5, None, "normal", "stalled_progress"),
        (DEMO_ESCALATION_CONFIG, 6, CONTEXT, "elevated", "prolonged_stalled_progress"),
    ],
)
def test_requested_scenarios(config, seconds, context, priority, reason):
    result = evaluate_escalation(ProgressState("stalled", seconds), context, config=config)
    assert result.should_evaluate == (priority is not None)
    assert result.priority == priority
    assert result.reason == reason


@pytest.mark.parametrize("config", [DEFAULT_ESCALATION_CONFIG, DEMO_ESCALATION_CONFIG])
def test_exact_thresholds(config):
    for threshold, context in [
        (config.expression_assisted_seconds, CONTEXT),
        (config.normal_stall_seconds, None),
    ]:
        before = evaluate_escalation(
            ProgressState("stalled", threshold - 0.001), context, config=config
        )
        assert before.should_evaluate == (threshold > config.normal_stall_seconds)
        if before.should_evaluate:
            assert before.priority == "normal"
        assert evaluate_escalation(
            ProgressState("stalled", threshold), context, config=config
        ).should_evaluate
    assert (
        evaluate_escalation(
            ProgressState("stalled", config.prolonged_stall_seconds), config=config
        ).reason
        == "prolonged_stalled_progress"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"label": "neutral"},
        {"probability": 0.49},
        {"duration_seconds": 4.9},
        {"duration_seconds": None},
    ],
)
def test_nonqualifying_expression(changes):
    context = ExpressionContext.model_validate(CONTEXT.model_dump() | changes)
    assert not evaluate_escalation(ProgressState("stalled", 7), context).should_evaluate


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_stall_duration(value):
    with pytest.raises(ValueError):
        evaluate_escalation(ProgressState("stalled", value))


def test_config_validation():
    with pytest.raises(ValueError):
        EscalationConfig(normal_stall_seconds=3)
    with pytest.raises(ValueError):
        EscalationConfig(expression_min_probability=2)


def test_demo_pipeline_branches_are_reachable():
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from agent.progress import DEMO_PROGRESS_WINDOW_SECONDS, ProgressEvaluator
    from shared.contracts import Activity, SeatState

    activity = Activity(
        id="task", name="Task", check_type="gesture", success_threshold=0.8, no_progress_seconds=30
    )
    demo = ProgressEvaluator(activity, window_seconds=DEMO_PROGRESS_WINDOW_SECONDS)
    classroom = ProgressEvaluator(activity)
    start = datetime(2026, 11, 14, tzinfo=UTC)
    for seconds in range(7):
        now = start + timedelta(seconds=seconds)
        snapshot = SeatState(
            session_id=UUID(int=1),
            seat_id="S1-L",
            activity_id="task",
            status="in_progress",
            tracking_valid=True,
            task_score=0.2,
            updated_at=now,
        )
        progress = demo.update(snapshot, now=now)
        default_progress = classroom.update(snapshot, now=now)
        if seconds == 2:
            assert progress.trend == "stalled"
            assert default_progress.trend == "unknown"
        context = ExpressionContext(label="sadness", probability=0.62, duration_seconds=seconds)
        result = evaluate_escalation(progress, context, config=DEMO_ESCALATION_CONFIG)
        without = evaluate_escalation(progress, config=DEMO_ESCALATION_CONFIG)
        if seconds < 4:
            assert not result.should_evaluate and not without.should_evaluate
        elif seconds == 4:
            assert result.priority == without.priority == "normal"
        elif seconds == 5:
            assert result.reason == "stalled_progress_with_expression_context"
            assert result.priority == "elevated" and without.priority == "normal"
        else:
            assert result.reason == without.reason == "prolonged_stalled_progress"
            assert result.priority == without.priority == "elevated"
    assert DEFAULT_ESCALATION_CONFIG.expression_min_duration_seconds == 5
    assert DEMO_ESCALATION_CONFIG.expression_min_duration_seconds == 5


def test_demo_brief_expression_does_not_elevate():
    context = ExpressionContext(label="sadness", probability=0.62, duration_seconds=4.99)
    result = evaluate_escalation(
        ProgressState("stalled", 5), context, config=DEMO_ESCALATION_CONFIG
    )
    assert result.should_evaluate and result.priority == "normal"
