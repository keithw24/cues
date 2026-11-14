from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.router import EvaluationRouter
from shared.contracts import SeatState

NORMAL = EscalationDecision(True, "normal", "stalled_progress")
EXPRESSION = EscalationDecision(True, "elevated", "stalled_progress_with_expression_context")
PROLONGED = EscalationDecision(True, "elevated", "prolonged_stalled_progress")
STALL = ProgressState("stalled", 10)


def snapshot(**changes):
    return SeatState.model_validate(
        dict(
            session_id=UUID(int=1),
            seat_id="A",
            activity_id="raise_hand",
            updated_at=datetime(2026, 11, 14, tzinfo=UTC),
            status="in_progress",
            tracking_valid=True,
        )
        | changes
    )


def test_first_request_and_repeated_duplicates():
    router = EvaluationRouter()
    seat = snapshot()
    request = router.route(seat, STALL, NORMAL)
    assert request.session_id == seat.session_id
    assert request.seat_id == "A" and request.activity_id == "raise_hand"
    assert request.observed_at == seat.updated_at
    assert request.progress is STALL and request.escalation is NORMAL
    for _ in range(5):
        assert router.route(seat, STALL, NORMAL) is None


@pytest.mark.parametrize("trend", ["improving", "completed"])
def test_recovery_or_completion_resets(trend):
    router = EvaluationRouter()
    seat = snapshot()
    assert router.route(seat, STALL, NORMAL)
    assert router.route(seat, ProgressState(trend), NORMAL) is None
    assert router.route(seat, STALL, NORMAL)


def test_unknown_and_tracking_loss_pause_without_rearming():
    router = EvaluationRouter()
    seat = snapshot()
    assert router.route(seat, ProgressState("unknown"), NORMAL) is None
    assert router.route(seat, STALL, NORMAL)
    assert (
        router.route(
            snapshot(tracking_valid=False, status="tracking_lost"), ProgressState("unknown"), NORMAL
        )
        is None
    )
    assert router.route(snapshot(tracking_valid=False), STALL, PROLONGED) is None
    assert router.route(seat, STALL, NORMAL) is None
    assert router.route(seat, ProgressState("stalled", 15), PROLONGED)


@pytest.mark.parametrize(
    "change", [{"seat_id": "B"}, {"activity_id": "other"}, {"session_id": UUID(int=2)}]
)
def test_task_identity_isolation(change):
    router = EvaluationRouter()
    assert router.route(snapshot(), STALL, NORMAL)
    assert router.route(snapshot(**change), STALL, NORMAL)
    assert router.route(snapshot(), STALL, NORMAL) is None


def test_upgrade_order_and_downgrade_suppression():
    router = EvaluationRouter()
    seat = snapshot()
    for decision in (NORMAL, EXPRESSION, PROLONGED):
        assert router.route(seat, STALL, decision)
        assert router.route(seat, STALL, decision) is None
    for decision in (NORMAL, EXPRESSION, PROLONGED):
        assert router.route(seat, STALL, decision) is None


def test_normal_can_upgrade_directly_to_prolonged():
    router = EvaluationRouter()
    assert router.route(snapshot(), STALL, NORMAL)
    assert router.route(snapshot(), STALL, PROLONGED)
    assert router.route(snapshot(), STALL, EXPRESSION) is None


def test_ineligible_decision_does_not_consume_or_reset_episode():
    router = EvaluationRouter()
    no = EscalationDecision(False)
    assert router.route(snapshot(), STALL, no) is None
    assert router.route(snapshot(), STALL, NORMAL)
    assert router.route(snapshot(), STALL, no) is None
    assert router.route(snapshot(), STALL, NORMAL) is None


def test_explicit_restart_and_missing_activity():
    router = EvaluationRouter()
    seat = snapshot()
    assert router.route(seat, STALL, NORMAL)
    router.reset(session_id=seat.session_id, seat_id=seat.seat_id, activity_id=seat.activity_id)
    assert router.route(seat, STALL, NORMAL)
    assert router.route(snapshot(activity_id=None), STALL, NORMAL) is None


def test_invalid_eligible_pair_does_not_consume_episode():
    router = EvaluationRouter()
    with pytest.raises(ValueError):
        router.route(snapshot(), STALL, EscalationDecision(True))
    assert router.route(snapshot(), STALL, NORMAL)
