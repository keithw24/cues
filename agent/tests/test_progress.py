from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from agent.progress import ProgressEvaluator
from shared.contracts import Activity, SeatState

START = datetime(2026, 11, 14, tzinfo=UTC)


def activity(threshold=0.8, check_type="gesture"):
    return Activity(
        id="task",
        name="Task",
        check_type=check_type,
        success_threshold=threshold,
        no_progress_seconds=30,
    )


def sample(seconds, score=None, **changes):
    return SeatState.model_validate(
        dict(
            session_id=UUID(int=1),
            seat_id="S1-L",
            activity_id="task",
            status="in_progress",
            task_score=score,
            tracking_valid=True,
            updated_at=START + timedelta(seconds=seconds),
        )
        | changes
    )


def feed(evaluator, scores):
    return [
        evaluator.update(sample(i, score), now=START + timedelta(seconds=i))
        for i, score in enumerate(scores)
    ]


@pytest.mark.parametrize(
    ("scores", "trend"),
    [
        ([0.20, 0.34, 0.49, 0.61, 0.72], "improving"),
        ([0.20, 0.27, 0.31, 0.29, 0.30, 0.28], "stalled"),
        ([0.31, 0.32, 0.30, 0.33, 0.31], "stalled"),
    ],
)
def test_trends(scores, trend):
    result = feed(ProgressEvaluator(activity()), scores)[-1]
    assert result.trend == trend
    assert result.stalled_seconds == (len(scores) - 1 if trend == "stalled" else 0)


def test_completion_uses_activity_threshold_immediately_and_latches():
    evaluator = ProgressEvaluator(activity(0.65))
    assert feed(evaluator, [0.66])[0].trend == "completed"
    assert evaluator.update(sample(1, 0.1), now=START + timedelta(seconds=1)).trend == "completed"
    evaluator.reset()
    assert feed(evaluator, [0.1])[0].trend == "unknown"


def test_explicit_completion_for_boolean_task():
    evaluator = ProgressEvaluator(activity(None, "rule"))
    assert evaluator.update(sample(0, status="done"), now=START).trend == "completed"


def test_tracking_loss_and_recovery_reset_timing():
    evaluator = ProgressEvaluator(activity())
    for i in range(6):
        result = evaluator.update(
            sample(i, 0.2, tracking_valid=i == 0), now=START + timedelta(seconds=i)
        )
        assert result.trend == "unknown"
    for i in range(6, 11):
        result = evaluator.update(sample(i, 0.2), now=START + timedelta(seconds=i))
    assert result.trend == "stalled"
    assert result.stalled_seconds == 4


def test_irregular_timestamps_and_gap():
    evaluator = ProgressEvaluator(activity())
    for t in [0, 0.7, 1.8, 3, 4.2]:
        result = evaluator.update(sample(t, 0.2), now=START + timedelta(seconds=t))
    assert result.trend == "stalled"
    assert result.stalled_seconds == 4.2
    assert evaluator.update(sample(9, 0.2), now=START + timedelta(seconds=9)).trend == "unknown"


def test_duplicates_do_not_accumulate_and_staleness_clears():
    evaluator = ProgressEvaluator(activity())
    state = feed(evaluator, [0.2] * 5)[-1]
    assert evaluator.update(sample(4, 0.2), now=START + timedelta(seconds=4)) == state
    assert evaluator.update(sample(4, 0.2), now=START + timedelta(seconds=9)).trend == "unknown"


def test_task_change_and_missing_score_clear_history():
    evaluator = ProgressEvaluator(activity())
    feed(evaluator, [0.2] * 5)
    assert evaluator.update(sample(5), now=START + timedelta(seconds=5)).trend == "unknown"
    assert (
        evaluator.update(
            sample(6, 0.2, activity_id="other"), now=START + timedelta(seconds=6)
        ).trend
        == "unknown"
    )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_configuration_validation(value):
    with pytest.raises(ValueError):
        ProgressEvaluator(activity(), window_seconds=value)


def test_hysteresis_preserves_improvement_inside_noise_band():
    evaluator = ProgressEvaluator(activity())
    assert feed(evaluator, [0.2, 0.25, 0.35, 0.4, 0.45])[-1].trend == "improving"
    # Next delta is below the 0.10 entry threshold but above the 0.05 exit threshold.
    result = evaluator.update(sample(5, 0.4), now=START + timedelta(seconds=5))
    assert result.trend == "improving"
    assert result.stalled_seconds == 0
