from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agent.deep_agent import create_cues_deep_agent
from agent.escalation import DEMO_ESCALATION_CONFIG
from agent.progress_history import ProgressHistoryStore
from agent.seat_state_runtime import (
    SeatStatePipeline,
    SeatStateRuntime,
    SupabaseSeatStateSource,
)
from agent.teacher_review import TeacherReviewStore
from shared.contracts import Activity, SeatState

START = datetime(2026, 11, 14, tzinfo=UTC)


def activity(activity_id="task", check_type="rule"):
    return Activity(
        id=activity_id,
        name=activity_id,
        check_type=check_type,
        success_threshold=0.9 if check_type == "gesture" else None,
        no_progress_seconds=30,
    )


def snapshot(seconds, *, seat="A", activity_id="task", score=None, **changes):
    return SeatState.model_validate(
        {
            "session_id": UUID(int=1),
            "seat_id": seat,
            "activity_id": activity_id,
            "status": "in_progress",
            "tracking_valid": True,
            "task_score": score,
            "updated_at": START + timedelta(seconds=seconds),
        }
        | changes
    )


class RecordingAgent:
    def __init__(self, *, fail_seat=None):
        self.contexts = []
        self.fail_seat = fail_seat

    def run(self, context):
        if context.request.seat_id == self.fail_seat:
            raise RuntimeError("provider unavailable")
        self.contexts.append(context)
        return SimpleNamespace(assessment="ok", pending_review=None)


def pipeline(activities=None, agent=None):
    history = ProgressHistoryStore()
    return SeatStatePipeline(
        activities or [activity()],
        agent or RecordingAgent(),
        history,
        progress_window_seconds=2,
        escalation_config=DEMO_ESCALATION_CONFIG,
        clock=lambda: START + timedelta(seconds=20),
    )


def feed(target, rows):
    return [target.process_row(row, now=row.updated_at) for row in rows]


def test_improving_state_does_not_route():
    target = pipeline([activity(check_type="gesture")])
    results = feed(target, [snapshot(i, score=s) for i, s in enumerate([0.2, 0.34, 0.49])])
    assert results[-1].progress.trend == "improving"
    assert results[-1].request is None
    assert target.agent.contexts == []


def test_stalled_state_routes_through_enricher_and_agent():
    target = pipeline()
    results = feed(target, [snapshot(i) for i in range(5)])
    routed = results[-1]
    assert routed.progress.trend == "stalled"
    assert routed.escalation.should_evaluate
    assert routed.request is not None and routed.agent_result is not None
    assert target.agent.contexts[0].activity.id == "task"
    assert target.agent.contexts[0].request is routed.request


def test_tracking_loss_never_routes_or_turns_null_score_into_failure():
    target = pipeline()
    results = feed(
        target,
        [
            snapshot(i, tracking_valid=False, status="tracking_lost", task_score=None)
            for i in range(8)
        ],
    )
    assert all(result.progress.trend == "unknown" for result in results)
    assert all(not result.escalation.should_evaluate for result in results)
    assert target.agent.contexts == []


def test_exact_unchanged_row_is_not_processed_twice():
    target = pipeline()
    row = snapshot(0)
    assert target.process_row(row, now=row.updated_at) is not None
    assert target.process_row(row, now=row.updated_at) is None
    history = target.history.get_recent_progress_history(UUID(int=1), "A", "task")
    assert len(history) == 1


def test_activity_change_partitions_progress_state():
    target = pipeline([activity("task"), activity("other")])
    feed(target, [snapshot(i) for i in range(3)])
    changed = target.process_row(snapshot(3, activity_id="other"), now=START + timedelta(seconds=3))
    assert changed.progress.trend == "unknown"
    assert len(target._evaluators) == 2


def test_expression_only_elevates_existing_stall():
    without = pipeline()
    plain = feed(without, [snapshot(i) for i in range(6)])[-1]
    with_expression = pipeline()
    rows = [snapshot(i) for i in range(5)] + [
        snapshot(
            5,
            expression_context={
                "label": "sadness",
                "probability": 0.62,
                "duration_seconds": 5,
                "supporting_only": True,
            },
        )
    ]
    supported = feed(with_expression, rows)[-1]
    assert plain.escalation.priority == "normal"
    assert supported.escalation.priority == "elevated"
    isolated = pipeline().process_row(rows[-1], now=rows[-1].updated_at)
    assert not isolated.escalation.should_evaluate


class FakeSource:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self):
        return self.rows


def test_one_bad_seat_does_not_corrupt_another(caplog):
    target = pipeline()
    runtime = SeatStateRuntime(
        FakeSource([{"seat_id": "bad"}, snapshot(0, seat="good")]), target
    )
    results = runtime.run_once()
    assert [result.snapshot.seat_id for result in results] == ["good"]
    assert "SeatState processing failed for seat bad" in caplog.text


def test_agent_failure_for_one_seat_does_not_stop_next_seat(caplog):
    agent = RecordingAgent(fail_seat="bad")
    target = pipeline(agent=agent)
    # Warm both streams until the next row becomes eligible.
    feed(target, [snapshot(i, seat=seat) for i in range(4) for seat in ("bad", "good")])
    target.clock = lambda: START + timedelta(seconds=4)
    runtime = SeatStateRuntime(
        FakeSource([snapshot(4, seat="bad"), snapshot(4, seat="good")]), target
    )
    results = runtime.run_once()
    assert [result.snapshot.seat_id for result in results] == ["good"]
    assert agent.contexts[0].request.seat_id == "good"
    assert "RuntimeError" in caplog.text


def test_supabase_source_selects_only_contract_fields():
    response = SimpleNamespace(data=[snapshot(0).model_dump(mode="json")])
    query = SimpleNamespace(execute=lambda: response)

    class Table:
        def __init__(self):
            self.fields = None

        def select(self, fields):
            self.fields = fields
            return query

    table = Table()
    client = SimpleNamespace(table=lambda name: table if name == "seat_state" else None)
    rows = SupabaseSeatStateSource(client).fetch()
    assert rows == response.data
    assert "tracking_valid" in table.fields and "expression_context" in table.fields


class ActionModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_orchestrator_reaches_existing_review_storage_action_path():
    model = ActionModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "request_teacher_review",
                        "id": "review",
                        "args": {
                            "rationale": "Repeated stalled progress warrants teacher review.",
                            "evidence_used": ["current_progress"],
                        },
                    }
                ],
            )
        ]
    )
    history = ProgressHistoryStore()
    reviews = TeacherReviewStore()
    agent = create_cues_deep_agent(model, history, reviews=reviews)
    target = SeatStatePipeline(
        [activity()],
        agent,
        history,
        progress_window_seconds=2,
        escalation_config=DEMO_ESCALATION_CONFIG,
    )
    result = feed(target, [snapshot(i) for i in range(5)])[-1]
    assert result.agent_result.pending_review is not None
    assert reviews.get_pending_reviews() == [result.agent_result.pending_review]
