from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent.progress import ProgressEvaluator
from shared.contracts import Activity, SeatState


def test_progress_scenarios():
    activity = Activity(
        id="gesture",
        name="Gesture",
        check_type="gesture",
        success_threshold=0.8,
        no_progress_seconds=6,
    )
    for scores, expected in [
        ([0.2] * 7, "evaluate_agent"),
        ([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], "wait"),
    ]:
        evaluator = ProgressEvaluator(activity)
        for i, score in enumerate(scores):
            now = datetime(2026, 11, 14, tzinfo=UTC) + timedelta(seconds=i)
            state = SeatState(
                session_id=UUID(int=1),
                seat_id="S1-L",
                activity_id="gesture",
                status="in_progress",
                task_score=score,
                tracking_valid=True,
                updated_at=now,
            )
            decision = evaluator.update(state, now=now)
        assert decision.action == expected
        now += timedelta(seconds=1)
        state.updated_at = now
        assert evaluator.update(state, now=now).action == "wait"
        state.status = "done"
        state.updated_at = now + timedelta(seconds=1)
        assert evaluator.update(state, now=state.updated_at).action == "completed"


def test_tracking_loss_resets_history():
    activity = Activity(id="raise", name="Raise", check_type="rule", no_progress_seconds=2)
    evaluator = ProgressEvaluator(activity)
    for i, valid in enumerate([True, True, False, True, True, True]):
        now = datetime(2026, 11, 14, tzinfo=UTC) + timedelta(seconds=i)
        state = SeatState(
            session_id=UUID(int=1),
            seat_id="S1-L",
            activity_id="raise",
            status="in_progress",
            tracking_valid=valid,
            updated_at=now,
        )
        result = evaluator.update(state, now=now)
        assert (result.action == "evaluate_agent") == (i == 5)
