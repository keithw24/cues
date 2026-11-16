"""Contract: what Python produces is accepted by the dashboard's real TypeScript parsers."""

import shutil
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from shared.contracts import ExpressionContext, SeatState, SeatStatus
from tests.contract.fixtures import fixture_rows
from tests.support.typescript import run_parser

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(not shutil.which("node"), reason="node is not installed"),
]


def test_dashboard_status_vocabulary_equals_the_python_contract():
    ts = set(run_parser("vocabulary", {})["statuses"])
    assert ts == {status.value for status in SeatStatus}


def seat_states() -> list[dict]:
    """Every shape vision can publish: each status, nulls cleared, expression context present."""
    now = datetime.now(UTC)
    session = uuid4()
    rows = [
        SeatState(seat_id=f"S1-P{i}", session_id=session, status=status, updated_at=now)
        for i, status in enumerate(SeatStatus, start=1)
    ]
    rows.append(
        SeatState(
            seat_id="S1-P9",
            session_id=session,
            status=SeatStatus.IN_PROGRESS,
            updated_at=now,
            activity_id="thumbs_up",
            tracking_valid=True,
            session_revision=3,
            task_score=0.42,
            expression_context=ExpressionContext(
                label="sadness", probability=0.7, duration_seconds=6.0
            ),
        )
    )
    return [row.model_dump(mode="json") for row in rows] + fixture_rows(
        "seat_states.json", SeatState
    )


def test_every_seat_state_vision_can_publish_is_accepted_by_the_dashboard_parser():
    states = seat_states()
    seats = [
        {
            "id": s["seat_id"],
            "station_id": "S1",
            "side": None,
            "display_name": s["seat_id"],
            "is_simulated": False,
        }
        for s in {s["seat_id"]: s for s in states}.values()
    ]
    snapshot = {
        "seats": seats,
        "states": states,
        "activities": [{"id": "thumbs_up", "name": "Thumbs up"}],
        "stations": [{"id": "S1", "name": "Station S1"}],
    }
    assert run_parser("snapshot", snapshot)["states"] == len(states)


def test_the_dashboard_parser_rejects_what_the_contract_forbids():
    """The parsers must be strict in the same places the Python contract is."""
    bad = seat_states()[0] | {"status": "daydreaming"}
    snapshot = {"seats": [], "states": [bad], "activities": [], "stations": []}
    with pytest.raises(AssertionError, match="rejected"):
        run_parser("snapshot", snapshot)
