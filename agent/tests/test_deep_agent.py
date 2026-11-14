import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import Field, ValidationError

from agent.context_enricher import EnrichedEvaluationContext
from agent.deep_agent import AgentAssessment, create_cues_deep_agent
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.router import AgentEvaluationRequest
from shared.contracts import Activity, CheckType, SeatState


class ToolModel(FakeMessagesListChatModel):
    seen: list = Field(default_factory=list)
    offered: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self.offered.append([getattr(t, "name", None) for t in tools])
        return self

    def _generate(self, messages, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, **kwargs)


def context():
    return EnrichedEvaluationContext(
        AgentEvaluationRequest(
            UUID(int=1),
            "A",
            "task",
            datetime(2026, 11, 14, tzinfo=UTC),
            ProgressState("stalled", 10),
            EscalationDecision(True, "normal", "stalled_progress"),
        ),
        Activity(id="task", name="Raise hand", check_type="rule", no_progress_seconds=30),
    )


def assessment():
    return AIMessage(
        content="",
        tool_calls=[
            dict(
                name="AgentAssessment",
                id="assessment",
                args=dict(
                    decision="continue_monitoring",
                    rationale="Available evidence is limited.",
                    evidence_used=["current_progress"],
                ),
            )
        ],
    )


def test_direct_assessment_and_serialized_context():
    model = ToolModel(responses=[assessment()])
    result = create_cues_deep_agent(model, ProgressHistoryStore()).assess(context())
    assert isinstance(result, AgentAssessment)
    assert result.decision == "continue_monitoring"
    payload = json.loads(model.seen[0][-1].content)
    assert payload["request"]["session_id"] == str(UUID(int=1))
    assert payload["activity"]["name"] == "Raise hand"
    assert "no_progress_seconds" not in payload["activity"]
    assert set(payload["activity"]) == {
        "id",
        "name",
        "check_type",
        "success_threshold",
        "review_threshold",
    }
    assert payload["request"]["progress"]["stalled_seconds"] == 10
    assert len(model.seen) == 1
    assert set(model.offered[0]) == {
        "get_recent_progress_history",
        "get_prompt_history",
        "AgentAssessment",
    }


def test_history_tool_result_reenters_same_run_and_is_scoped():
    current = context()
    store = ProgressHistoryStore()
    for seat in ["A", "B"]:
        store.record(
            SeatState(
                session_id=UUID(int=1),
                seat_id=seat,
                activity_id="task",
                status="done",
                updated_at=current.request.observed_at,
            ),
            ProgressState("completed" if seat == "A" else "unknown"),
        )
    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[dict(name="get_recent_progress_history", id="history", args={})],
            ),
            assessment(),
        ]
    )
    result = create_cues_deep_agent(model, store).assess(current)
    assert result.decision == "continue_monitoring"
    assert len(model.seen) == 2
    outputs = [m for m in model.seen[1] if isinstance(m, ToolMessage)]
    assert len(outputs) == 1
    assert "completed" in outputs[0].content and "unknown" not in outputs[0].content
    for offered in model.offered:
        assert set(offered) == {
            "get_recent_progress_history",
            "get_prompt_history",
            "AgentAssessment",
        }


def test_assessment_schema_validation():
    with pytest.raises(ValidationError):
        AgentAssessment(decision="change_instruction", rationale="unsupported")
    with pytest.raises(ValidationError):
        AgentAssessment(decision="continue_monitoring", rationale=" ")


def test_mismatched_activity_rejected():
    current = context()
    current.activity.id = "other"
    with pytest.raises(ValueError, match="activity"):
        create_cues_deep_agent(ToolModel(responses=[assessment()]), ProgressHistoryStore()).assess(
            current
        )


def test_agent_serialization_preserves_original_activity_and_criteria():
    from agent.deep_agent import serialize_agent_context

    current = context()
    current.activity.check_type = CheckType.GESTURE
    current.activity.success_threshold = 0.78
    current.activity.review_threshold = 0.58
    payload = json.loads(serialize_agent_context(current))
    assert payload["activity"]["success_threshold"] == 0.78
    assert payload["activity"]["review_threshold"] == 0.58
    assert current.activity.no_progress_seconds == 30
    assert "no_progress_seconds" not in payload["activity"]


def test_empty_history_is_json_text_in_same_run():
    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[dict(name="get_recent_progress_history", id="history", args={})],
            ),
            assessment(),
        ]
    )
    result = create_cues_deep_agent(model, ProgressHistoryStore()).assess(context())
    assert result.decision == "continue_monitoring"
    outputs = [m for m in model.seen[1] if isinstance(m, ToolMessage)]
    assert outputs[0].content == "[]"


def history_call(identifier="history", limit=10):
    return AIMessage(
        content="",
        tool_calls=[dict(name="get_recent_progress_history", id=identifier, args={"limit": limit})],
    )


@pytest.mark.parametrize("decision", ["continue_monitoring", "teacher_review_warranted"])
def test_empty_history_is_not_evidence_for_either_decision(decision):
    from agent.deep_agent import validate_assessment

    result = dict(
        structured_response=dict(
            decision=decision,
            rationale="Assessment relies on the current episode only.",
            evidence_used=["current_progress"],
        ),
        messages=[ToolMessage(content="[]", name="get_recent_progress_history", tool_call_id="h")],
    )
    assert validate_assessment(result).decision == decision
    result["structured_response"]["evidence_used"] = ["recent_progress_history"]
    with pytest.raises(ValueError, match="unavailable history"):
        validate_assessment(result)


@pytest.mark.parametrize("labels", [["emotion"], [], ["activity", "activity"]])
def test_evidence_labels_are_constrained(labels):
    with pytest.raises(ValidationError):
        AgentAssessment(
            decision="continue_monitoring", rationale="Current evidence.", evidence_used=labels
        )


def test_rationale_is_bounded():
    with pytest.raises(ValidationError):
        AgentAssessment(
            decision="continue_monitoring", rationale="x" * 501, evidence_used=["current_progress"]
        )


def test_history_bound_and_sequential_duplicate_cache(monkeypatch):
    from datetime import timedelta

    current = context()
    store = ProgressHistoryStore()
    for seconds in range(20):
        store.record(
            SeatState(
                session_id=current.request.session_id,
                seat_id="A",
                activity_id="task",
                status="in_progress",
                updated_at=current.request.observed_at - timedelta(seconds=seconds),
            ),
            ProgressState("stalled", seconds),
        )
    original = store.get_recent_progress_history
    reads = []

    def counted(*args, **kwargs):
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "get_recent_progress_history", counted)
    model = ToolModel(responses=[history_call("h1"), history_call("h2"), assessment()])
    create_cues_deep_agent(model, store).assess(current)
    assert len(reads) == 1
    outputs = [m for m in model.seen[-1] if isinstance(m, ToolMessage)]
    assert len(outputs) == 2
    assert len(json.loads(outputs[0].content)) == 10
    assert outputs[0].content == outputs[1].content


def test_model_step_budget():
    from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError

    from agent.deep_agent import AgentBudgets

    model = ToolModel(responses=[history_call(), assessment()])
    agent = create_cues_deep_agent(
        model, ProgressHistoryStore(), budgets=AgentBudgets(max_model_steps=1)
    )
    with pytest.raises(ModelCallLimitExceededError):
        agent.assess(context())
    assert len(model.seen) == 1


def test_domain_tool_attempt_budget_includes_duplicates():
    from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

    from agent.deep_agent import AgentBudgets

    model = ToolModel(responses=[history_call("h1"), history_call("h2"), assessment()])
    agent = create_cues_deep_agent(
        model, ProgressHistoryStore(), budgets=AgentBudgets(max_domain_tool_calls=1)
    )
    with pytest.raises(ToolCallLimitExceededError):
        agent.assess(context())
    assert len(model.seen) == 2


def test_evidence_history_available_only_after_nonempty_success():
    from agent.deep_agent import validate_assessment

    output = dict(
        decision="teacher_review_warranted",
        rationale="Repeated recorded stalls.",
        evidence_used=["current_progress", "recent_progress_history"],
    )
    with pytest.raises(ValueError):
        validate_assessment(dict(structured_response=output, messages=[]))
    message = ToolMessage(
        content='[{"progress":{"trend":"stalled","stalled_seconds":10}}]',
        name="get_recent_progress_history",
        tool_call_id="h",
    )
    assert (
        validate_assessment(dict(structured_response=output, messages=[message])).decision
        == output["decision"]
    )


def test_default_model_budget_is_four_steps():
    from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError

    from agent.deep_agent import AgentBudgets

    assert AgentBudgets().max_model_steps == 4
    assert AgentBudgets().max_domain_tool_calls == 3
    model = ToolModel(responses=[history_call(f"h{i}") for i in range(5)])
    with pytest.raises(ModelCallLimitExceededError):
        create_cues_deep_agent(
            model, ProgressHistoryStore(), budgets=AgentBudgets(max_domain_tool_calls=10)
        ).assess(context())
    assert len(model.seen) == 4


def test_tool_rejects_history_limit_over_ten():
    model = ToolModel(responses=[history_call(limit=11), assessment()])
    # ValueError from tool input is surfaced; no oversized context can reach model.
    with pytest.raises(ValueError, match="between 1 and 10"):
        create_cues_deep_agent(model, ProgressHistoryStore()).assess(context())


def test_prompt_tool_feedback_and_evidence():
    from agent.prompt_history import PromptHistoryEntry, PromptHistoryStore

    current = context()
    store = PromptHistoryStore()
    store.record(
        current.request.session_id,
        "A",
        "task",
        PromptHistoryEntry(observed_at=current.request.observed_at, outcome="prompted_correct"),
    )
    final = assessment()
    final.tool_calls[0]["args"]["evidence_used"] = ["current_progress", "prompt_history"]
    model = ToolModel(
        responses=[
            AIMessage(content="", tool_calls=[dict(name="get_prompt_history", id="p", args={})]),
            final,
        ]
    )
    result = create_cues_deep_agent(model, ProgressHistoryStore(), prompt_history=store).assess(
        current
    )
    assert "prompt_history" in result.evidence_used
    assert (
        "prompted_correct" in next(m for m in model.seen[1] if isinstance(m, ToolMessage)).content
    )


@pytest.mark.parametrize(
    "messages", [[], [ToolMessage(content="[]", name="get_prompt_history", tool_call_id="p")]]
)
def test_unavailable_prompt_history_is_not_evidence(messages):
    from agent.deep_agent import validate_assessment

    with pytest.raises(ValueError, match="unavailable history"):
        validate_assessment(
            dict(
                messages=messages,
                structured_response=dict(
                    decision="continue_monitoring",
                    rationale="Current episode.",
                    evidence_used=["prompt_history"],
                ),
            )
        )


def test_budget_is_shared_across_tools():
    from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

    from agent.deep_agent import AgentBudgets

    model = ToolModel(
        responses=[
            history_call(),
            AIMessage(content="", tool_calls=[dict(name="get_prompt_history", id="p", args={})]),
            assessment(),
        ]
    )
    with pytest.raises(ToolCallLimitExceededError):
        create_cues_deep_agent(
            model, ProgressHistoryStore(), budgets=AgentBudgets(max_domain_tool_calls=1)
        ).assess(context())


def test_both_tools_feed_same_run_and_prompt_cache_is_separate(monkeypatch):
    from agent.prompt_history import PromptHistoryEntry, PromptHistoryStore

    current = context()
    prompts = PromptHistoryStore()
    prompts.record(
        current.request.session_id,
        "A",
        "task",
        PromptHistoryEntry(observed_at=current.request.observed_at, outcome="independent_correct"),
    )
    progress = ProgressHistoryStore()
    progress.record(
        SeatState(
            session_id=current.request.session_id,
            seat_id="A",
            activity_id="task",
            status="in_progress",
            updated_at=current.request.observed_at,
        ),
        ProgressState("stalled", 10),
    )
    original = prompts.get_prompt_history
    reads = []

    def counted(*args, **kwargs):
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(prompts, "get_prompt_history", counted)

    def prompt_call(identifier):
        return AIMessage(
            content="", tool_calls=[dict(name="get_prompt_history", id=identifier, args={})]
        )

    final = assessment()
    final.tool_calls[0]["args"]["evidence_used"] = ["recent_progress_history", "prompt_history"]
    model = ToolModel(responses=[history_call(), prompt_call("p1"), prompt_call("p2"), final])
    result = create_cues_deep_agent(model, progress, prompt_history=prompts).assess(current)
    assert set(result.evidence_used) == {"recent_progress_history", "prompt_history"}
    assert len(reads) == 1
    outputs = [m for m in model.seen[-1] if isinstance(m, ToolMessage)]
    assert "stalled" in outputs[0].content
    assert outputs[1].content == outputs[2].content
    assert "independent_correct" in outputs[1].content
