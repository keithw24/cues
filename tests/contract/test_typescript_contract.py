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


def test_a_number_typed_at_sign_up_becomes_a_number_the_backend_can_text():
    from shared.phone import is_e164

    typed = [["1", "(202) 555-0101"], ["44", "07946 123456"], ["1", "555"], ["", "123456789"]]
    numbers = run_parser("phone", {"numbers": typed})["numbers"]
    assert numbers[0] == "+12025550101" and numbers[1] == "+447946123456"
    assert numbers[2] is None and numbers[3] is None
    assert all(is_e164(n) for n in numbers if n is not None)


def test_the_profile_form_trims_and_refuses_numbers_the_database_would_refuse():
    cleaned = run_parser(
        "profile", {"display_name": "  Ms Rivera ", "phone_number": " +12025550101 "}
    )
    assert cleaned["display_name"] == "Ms Rivera" and cleaned["phone_number"] == "+12025550101"
    blank = run_parser("profile", {"display_name": "  ", "phone_number": ""})
    assert blank["display_name"] is None and blank["phone_number"] is None
    with pytest.raises(AssertionError, match="country code"):
        run_parser("profile", {"display_name": None, "phone_number": "(202) 555-0101"})
    with pytest.raises(AssertionError, match="80 characters"):
        run_parser("profile", {"display_name": "x" * 81, "phone_number": None})


# ---- The classroom: what the dashboard reads about a station --------------------------------


def test_a_new_teachers_default_station_answer_is_accepted():
    answer = {"station_id": "S12", "name": "Station S12", "created": True}
    assert run_parser("default_station", answer) == {
        "ok": True,
        "id": "S12",
        "name": "Station S12",
        "created": True,
    }
    for broken in ({**answer, "station_id": "bad id"}, {**answer, "created": "yes"}):
        with pytest.raises(AssertionError, match="rejected"):
            run_parser("default_station", broken)


def test_the_text_alert_state_follows_what_the_database_says():
    phone = "+12025550101"
    settings = {
        "notification_opt_in": True,
        "notification_phone": phone,
        "first_name": "Ana",
        "last_name": "Rivera",
        "photon_registration_status": "registering",
    }
    expected = {
        "registering": "activating",
        "registered": "enabled",
        "failed": "activation failed",
        "unregistered": "not enabled",
    }
    for status, state in expected.items():
        row = settings | {"photon_registration_status": status}
        assert run_parser("notification_state", {"settings": row, "phone": phone})["state"] == state
    # A different phone number, or an unsaved edit, never counts as consent.
    other = {"settings": settings, "phone": "+12025550102"}
    assert run_parser("notification_state", other)["state"] == "not enabled"
    unsaved = {"settings": settings, "phone": phone, "dirty": True}
    assert run_parser("notification_state", unsaved)["state"] == "not enabled"


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
    unknown_label = seat_states()[0] | {
        "expression_context": {"label": "calm", "probability": 0.7, "supporting_only": True}
    }
    with pytest.raises(AssertionError, match="rejected"):
        run_parser(
            "snapshot", {"seats": [], "states": [unknown_label], "activities": [], "stations": []}
        )
    not_supporting = seat_states()[0] | {
        "expression_context": {"label": "sadness", "probability": 0.7, "supporting_only": False}
    }
    with pytest.raises(AssertionError, match="rejected"):
        run_parser(
            "snapshot", {"seats": [], "states": [not_supporting], "activities": [], "stations": []}
        )


def test_a_person_the_camera_lost_is_never_shown_as_a_failed_attempt():
    row = next(r for r in seat_states() if r["status"] == "tracking_lost")
    now = datetime.now(UTC)
    options = {"enabled": True, "now": now.timestamp() * 1000, "connected": True}
    row = row | {"updated_at": now.isoformat()}
    shown = run_parser("observation", {"row": row, "options": options})
    assert shown["label"] == "Tracking lost" and shown["unavailable"] is True
    assert shown["needsReview"] is False and shown["score"] is None
    assert "not a failed attempt" in shown["detail"]


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


def test_mark_as_reviewed_answer_is_accepted_and_a_malformed_one_is_not():
    answer = {"closed": 1, "marked_at": datetime.now(UTC).isoformat()}
    assert run_parser("mark", answer)["closed"] == 1
    for broken in ({"closed": -1, "marked_at": answer["marked_at"]}, {"closed": 1}, None):
        with pytest.raises(AssertionError, match="rejected"):
            run_parser("mark", broken)


def test_the_timeline_flags_the_database_returns_are_accepted():
    now = datetime.now(UTC).isoformat()
    rows = [
        {"seat_id": "S1-P1", "kind": "review", "at": now},
        {"seat_id": "S1-P2", "kind": "no_progress", "at": now},
        {"seat_id": "S1-P3", "kind": "review_needed", "at": now},
    ]
    assert run_parser("flags", rows)["flags"] == [
        "review:S1-P1",
        "no_progress:S1-P2",
        "review_needed:S1-P3",
    ]
    for broken in (
        [{"seat_id": "S1-P1", "kind": "expression", "at": now}],
        [{"seat_id": "bad seat", "kind": "review", "at": now}],
    ):
        with pytest.raises(AssertionError, match="rejected"):
            run_parser("flags", broken)


def test_the_second_camera_warning_follows_the_writer_row():
    now = datetime.now(UTC)

    def conflict(contested_ago: float | None, seen_ago: float = 1.0) -> bool:
        row = {
            "seen_at": (now - timedelta(seconds=seen_ago)).isoformat(),
            "contested_at": None
            if contested_ago is None
            else (now - timedelta(seconds=contested_ago)).isoformat(),
        }
        return run_parser("writer", {"row": row, "now": now.timestamp() * 1000})["conflict"]

    assert conflict(contested_ago=1.5) is True  # another camera was refused a moment ago
    assert conflict(contested_ago=None) is False  # never contested
    assert conflict(contested_ago=60.0) is False  # long ago: the extra camera stopped
    assert conflict(contested_ago=1.5, seen_ago=120.0) is False  # the holder itself is gone


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


def test_the_insights_parser_rejects_what_the_contract_forbids():
    for broken in (
        {"supports": [{"action": "give_a_grade", "approved": 1, "resumed": 0}]},
        {"evidence": {"facial_expression": 2}},
        {"heat": [{"dow": 7, "hour": 10, "count": 1}]},
        {"weekly": [{"week_start": "last week", "sessions": 1, "reviews_raised": 1}]},
    ):
        with pytest.raises(AssertionError, match="rejected"):
            run_parser("insights", insights() | broken)
