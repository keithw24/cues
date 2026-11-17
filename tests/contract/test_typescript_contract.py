"""Contract: what Python produces is accepted by the dashboard's real TypeScript parsers."""

import shutil
from datetime import UTC, datetime
from typing import get_args
from uuid import uuid4

import pytest

from shared.contracts import (
    EvidenceSource,
    ExpressionContext,
    InsightsSummary,
    SeatState,
    SeatStatus,
)
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


def test_dashboard_evidence_vocabulary_equals_the_python_contract():
    assert set(run_parser("vocabulary", {})["evidence"]) == set(get_args(EvidenceSource))


def insights() -> dict:
    now = datetime.now(UTC).isoformat()
    return InsightsSummary.model_validate(
        {
            "range": {"from": now, "to": now},
            "totals": {
                "sessions": 2,
                "class_seconds": 900,
                "reviews_raised": 3,
                "confirmed": 1,
                "dismissed": 1,
                "reviewed": 1,
                "expired": 0,
                "pending": 0,
                "approved_supports": 1,
                "median_decision_seconds": 42.5,
            },
            "previous": {"sessions": 1, "reviews_raised": 2},
            "weekly": [{"week_start": "2026-11-09", "sessions": 2, "reviews_raised": 3}],
            "supports": [{"action": "show_example", "approved": 1, "resumed": 1}],
            "evidence": {"current_progress": 3, "activity": 2},
            "activities": [
                {
                    "activity_id": "raise_hand",
                    "name": "Raise hand",
                    "class_seconds": 900,
                    "reviews_raised": 3,
                }
            ],
            "heat": [{"dow": 2, "hour": 10, "count": 3}],
        }
    ).model_dump(mode="json", by_alias=True)


def test_an_insights_summary_python_produces_is_accepted_by_the_dashboard_parser():
    assert run_parser("insights", insights())["reviews"] == 3


def test_the_insights_parser_rejects_what_the_contract_forbids():
    for broken in (
        {"supports": [{"action": "give_a_grade", "approved": 1, "resumed": 0}]},
        {"evidence": {"facial_expression": 2}},
        {"heat": [{"dow": 7, "hour": 10, "count": 1}]},
        {"weekly": [{"week_start": "last week", "sessions": 1, "reviews_raised": 1}]},
    ):
        with pytest.raises(AssertionError, match="rejected"):
            run_parser("insights", insights() | broken)
