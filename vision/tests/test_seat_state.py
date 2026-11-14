"""SeatState as the primary input to the progress pipeline."""

import ast
import json
import uuid
from pathlib import Path

import numpy as np
import pytest

from shared.contracts import SeatState
from vision.activities import CurrentTasks
from vision.camera import Frame
from vision.events import Emitter, JsonlSink
from vision.people import PeopleGrouping
from vision.perception import Match
from vision.stages.s50_status import StatusStage

SESSION = uuid.UUID("00000000-0000-4000-8000-000000000001")
IMG = np.zeros((4, 4, 3), np.uint8)
VISION_EVENT_TYPES = {
    "attempt_success", "attempt_miss", "review_needed", "no_progress",
    "tracking_lost", "expression_context",
}  # fmt: skip


class RecordingEmitter:
    session_id = SESSION
    station_id = "S1"

    def __init__(self):
        self.events, self.states = [], []

    def emit(self, event):
        self.events.append(json.loads(event.model_dump_json()))

    def update_seat_state(self, state):
        self.states.append(json.loads(state.model_dump_json()))

    def close(self):
        pass


def ctx_for(score=None, seen=True, expression=None, task="raise_hand"):
    ctx = {"person_ids": ["S1-P1"], "people": {}, "faces": {}, "hands": {}, "match": {}}
    if seen:
        ctx["people"]["S1-P1"] = object()
        ctx["faces"]["S1-P1"] = object()
    if score is not None:
        ctx["match"]["S1-P1"] = Match(task, score)
    if expression is not None:
        ctx["expression"] = {"S1-P1": expression}
    return ctx


def run(stage, steps):
    """steps: list of (t, ctx)."""
    for i, (t, ctx) in enumerate(steps):
        stage.process(Frame(IMG, t, i), ctx)


def stage_for(task="raise_hand"):
    em = RecordingEmitter()
    return StatusStage(emitter=em, tasks=CurrentTasks(task), zones=PeopleGrouping()), em


def person_states(em):
    return [s for s in em.states if s["seat_id"] == "S1-P1"]


# ---- tracking_valid --------------------------------------------------------
def test_tracking_valid_survives_serialization_and_jsonl_upsert(tmp_path):
    state = SeatState(
        seat_id="S1-P1",
        session_id=SESSION,
        status="in_progress",
        updated_at="2026-11-14T05:00:00Z",
        activity_id="raise_hand",
        tracking_valid=False,
        task_score=None,
    )
    emitter = Emitter(JsonlSink(tmp_path), session_id=SESSION)
    emitter.update_seat_state(state)
    emitter.close()
    row = json.loads((tmp_path / "seat_state.json").read_text())["S1-P1"]
    assert row["tracking_valid"] is False
    assert SeatState.model_validate(row).tracking_valid is False


def test_tracking_loss_produces_tracking_valid_false():
    stage, em = stage_for()
    run(stage, [(i * 0.1, ctx_for(score=0.1)) for i in range(5)])
    run(stage, [(0.5 + i * 0.1, ctx_for(seen=False)) for i in range(50)])  # 5 s unseen
    states = person_states(em)
    assert states[-1]["status"] == "tracking_lost"
    assert states[-1]["tracking_valid"] is False
    assert states[-1]["task_score"] is None
    # tracking_valid turns false as soon as the person is not seen, before tracking_lost
    first_unseen = next(s for s in states if s["tracking_valid"] is False)
    assert first_unseen["status"] == "in_progress"


def test_valid_low_score_is_distinguishable_from_tracking_loss():
    stage, em = stage_for()
    run(stage, [(i * 0.1, ctx_for(score=0.05)) for i in range(30)])
    low = person_states(em)[-1]
    assert low["tracking_valid"] is True and low["task_score"] == pytest.approx(0.05)
    assert low["status"] in ("in_progress", "needs_help")
    run(stage, [(3.0 + i * 0.1, ctx_for(seen=False)) for i in range(40)])
    lost = person_states(em)[-1]
    assert lost["tracking_valid"] is False and lost["task_score"] is None


# ---- expression duration ---------------------------------------------------
def sad(p=0.63):
    base = dict.fromkeys(
        ["anger", "contempt", "disgust", "fear", "happiness", "neutral", "sadness", "surprise"], 0.0
    )
    base.update(sadness=p, neutral=round(1 - p, 3))
    return base


def test_expression_duration_is_preserved_when_qualified():
    stage, em = stage_for()
    run(stage, [(i * 0.1, ctx_for(score=0.1, expression=sad())) for i in range(60)])
    ctx = person_states(em)[-1]["expression_context"]
    assert ctx["label"] == "sadness"
    assert ctx["probability"] == pytest.approx(0.63)
    assert ctx["duration_seconds"] is not None and ctx["duration_seconds"] >= 5.0
    assert ctx["supporting_only"] is True


def test_expression_duration_is_never_null_once_seen():
    stage, em = stage_for()
    happy = {**sad(0.0), "happiness": 0.8, "neutral": 0.2}
    run(stage, [(i * 0.1, ctx_for(score=0.1, expression=happy)) for i in range(20)])
    ctx = person_states(em)[-1]["expression_context"]
    assert ctx["label"] == "happiness" and ctx["duration_seconds"] >= 1.0


def test_no_expression_without_a_face():
    stage, em = stage_for()
    run(stage, [(i * 0.1, ctx_for(score=0.1)) for i in range(5)])
    assert person_states(em)[-1]["expression_context"] is None


# ---- identity and freshness ------------------------------------------------
def test_seat_state_has_session_activity_and_required_fields():
    stage, em = stage_for("thumbs_up")
    run(stage, [(i * 0.1, ctx_for(score=0.3, task="thumbs_up")) for i in range(12)])
    row = person_states(em)[-1]
    for field in (
        "seat_id",
        "session_id",
        "activity_id",
        "status",
        "updated_at",
        "tracking_valid",
        "task_score",
    ):
        assert field in row
    assert row["session_id"] == str(SESSION)
    assert row["activity_id"] == "thumbs_up"
    SeatState.model_validate(row)


def test_seat_state_sent_about_once_per_second_and_on_changes():
    stage, em = stage_for()
    run(stage, [(i * 0.1, ctx_for(score=0.1)) for i in range(31)])  # 3 s, no status change
    assert 3 <= len(person_states(em)) <= 5
    before = len(person_states(em))
    run(stage, [(3.1, ctx_for(seen=False))])  # tracking changes: sent immediately
    assert len(person_states(em)) == before + 1


def test_updated_at_is_the_observation_time():
    import time
    from datetime import UTC, datetime

    stage, em = stage_for()
    observed = time.monotonic() - 5.0  # a frame captured 5 s ago
    stage.process(Frame(IMG, observed, 1), ctx_for(score=0.1))
    sent = datetime.fromisoformat(person_states(em)[-1]["updated_at"])
    age = (datetime.now(UTC) - sent).total_seconds()
    assert 4.0 <= age <= 7.0


# ---- vision makes no review or agent decision ------------------------------
def test_vision_only_emits_informational_event_types():
    stage, em = stage_for()
    steps = [(i * 0.1, ctx_for(score=s)) for i, s in enumerate([0.5] * 25 + [0.9] * 15)]
    run(stage, steps)
    assert {e["type"] for e in em.events} <= VISION_EVENT_TYPES


def test_vision_code_does_not_import_the_agent_or_write_alerts():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                assert not any(n.split(".")[0] == "agent" for n in names), path
        text = path.read_text()
        assert 'table("alerts")' not in text and "interventions" not in text, path
