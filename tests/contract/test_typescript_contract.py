"""Contract: what Python produces is accepted by the dashboard's real TypeScript code.

The dashboard is the last stop of a run. Everything vision, the agent and the database hand it
goes through the same parsers the browser uses (web/lib, run by node): what it accepts is
exactly what a teacher would see, and what it rejects is rejected for the teacher too.
"""

import shutil
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

import pytest

from shared.contracts import (
    INTERVENTION_MENU,
    EvidenceSource,
    ExpressionContext,
    InsightsSummary,
    SeatState,
    SeatStatus,
)
from tests.contract.fixtures import fixture_rows
from tests.support.typescript import run_parser
from tests.support.vision_harness import scripted_run, whole_class

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(not shutil.which("node"), reason="node is not installed"),
]


# ---- Identifiers and phone numbers: one rule, three implementations -------------------------


def test_station_ids_mean_the_same_in_vision_and_the_dashboard():
    from vision.station import STATION_ID_PATTERN

    samples = ["S1", "S12", "a_b-c", "x" * 64, "x" * 65, "", "bad id", "S1/P1", "S1é", "S 1"]
    python = [bool(STATION_ID_PATTERN.fullmatch(s)) for s in samples]
    assert run_parser("ids", {"stations": samples, "phones": []})["stations"] == python
    assert python[:4] == [True, True, True, True] and not any(python[4:])


def test_every_person_id_vision_issues_is_a_valid_seat_for_the_dashboard():
    from vision.people import MAX_PEOPLE, PersonTracker

    ids = [f"S7-P{n}" for n in range(1, MAX_PEOPLE + 1)]
    assert PersonTracker("S7")._new_id() == ids[0]
    assert all(run_parser("ids", {"stations": ids, "phones": []})["stations"])


def test_phone_numbers_mean_the_same_in_python_and_the_dashboard():
    from shared.phone import is_e164

    phones = ["+12025550101", "+441234567890", "12025550101", "+0123456789", "+1202", "", "+1 202"]
    assert run_parser("ids", {"stations": [], "phones": phones})["phones"] == [
        is_e164(p) for p in phones
    ]


# ---- The classroom: what the dashboard reads about a station --------------------------------


# ---- Vision: the seat state it publishes -------------------------------------------------------


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


def snapshot_of(states: list[dict]) -> dict:
    seats = [
        {
            "id": s["seat_id"],
            "station_id": s["seat_id"].rsplit("-", 1)[0],
            "side": None,
            "display_name": s["seat_id"],
            "is_simulated": False,
        }
        for s in {s["seat_id"]: s for s in states}.values()
    ]
    return {
        "seats": seats,
        "states": states,
        "activities": [{"id": "thumbs_up", "name": "Thumbs up"}],
        "stations": [{"id": "S1", "name": "Station S1"}],
    }


def test_every_seat_state_vision_can_publish_is_accepted_by_the_dashboard_parser():
    states = seat_states()
    assert run_parser("snapshot", snapshot_of(states))["states"] == len(states)


def test_what_the_real_status_stage_publishes_is_accepted_by_the_dashboard_parser():
    """Not hand-made rows: the rows vision's own status code produces over a whole class."""
    emitter, _ = scripted_run(whole_class())
    states = [s.model_dump(mode="json") for s in emitter.states]
    assert {s["status"] for s in states} == {status.value for status in SeatStatus}
    assert any(s["expression_context"] for s in states)
    assert run_parser("snapshot", snapshot_of(states))["states"] == len(states)


def test_the_dashboard_parser_rejects_what_the_contract_forbids():
    """The parsers must be strict in the same places the Python contract is."""
    bad = seat_states()[0] | {"status": "daydreaming"}
    snapshot = {"seats": [], "states": [bad], "activities": [], "stations": []}
    with pytest.raises(AssertionError, match="rejected"):
        run_parser("snapshot", snapshot)


# ---- The agent: what it publishes back for the dashboard ---------------------------------------


def test_evaluated_progress_the_agent_publishes_is_shown_by_the_dashboard():
    """SupabaseProgressPublisher's request, merged with the identifiers the database adds."""
    from agent.live_progress import SupabaseProgressPublisher
    from agent.progress import ProgressState
    from agent.progress_history import ProgressHistoryEntry

    calls: list[tuple[str, dict]] = []

    class Client:
        def rpc(self, name, args):
            calls.append((name, args))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))

    observed = datetime.now(UTC)
    snapshot = SeatState(
        seat_id="S1-P1",
        session_id=uuid4(),
        status="needs_help",
        updated_at=observed,
        activity_id="thumbs_up",
        tracking_valid=True,
        session_revision=2,
        task_score=0.1,
    )
    stalled = ProgressState("stalled", 6.0)
    recent = [ProgressHistoryEntry(observed_at=observed, progress=stalled)]
    since = observed - timedelta(seconds=6)
    assert SupabaseProgressPublisher(Client())(snapshot, stalled, recent, since) is True
    name, args = calls[0]
    assert name == "publish_task_progress"
    merged = args["p_progress"] | {
        "session_id": str(snapshot.session_id),
        "activity_id": snapshot.activity_id,
        "session_revision": snapshot.session_revision,
        "observed_at": args["p_observed_at"],
    }
    row = snapshot.model_dump(mode="json") | {"evaluated_progress": merged}
    now_ms = observed.timestamp() * 1000 + 1000
    shown = run_parser(
        "progress", {"row": row, "now": now_ms, "agent_seen_at": observed.isoformat()}
    )
    assert shown["visible"] and shown["trend"] == "stalled" and shown["recent"] == 1
    assert shown["stalled_since"] == since.isoformat()
    # Once the agent has been silent for 20 seconds the dashboard stops showing its numbers.
    quiet = run_parser(
        "progress", {"row": row, "now": now_ms + 25_000, "agent_seen_at": observed.isoformat()}
    )
    assert not quiet["visible"]


# ---- Reviews and supports ---------------------------------------------------------------------


def test_dashboard_evidence_vocabulary_equals_the_python_contract():
    assert set(run_parser("vocabulary", {})["evidence"]) == set(get_args(EvidenceSource))


def test_the_approved_support_menu_is_the_same_in_python_and_the_dashboard():
    assert run_parser("menu", {})["menu"] == INTERVENTION_MENU


def test_the_menu_never_describes_how_a_child_feels():
    """Supports are things an adult does: wording about a child's feelings is not allowed."""
    forbidden = ("feel", "anx", "upset", "angry", "sad", "frustrat", "distress", "emotion", "mood")
    for key, label in INTERVENTION_MENU.items():
        text = f"{key} {label}".lower()
        assert not any(word in text for word in forbidden), (key, label)


# ---- The end of a session: insights -------------------------------------------------------------


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
