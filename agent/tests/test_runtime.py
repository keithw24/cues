import json
import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from postgrest.exceptions import APIError

from agent import runtime
from agent.assessment import AgentAssessment
from agent.context_enricher import EnrichedEvaluationContext
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.router import AgentEvaluationRequest
from agent.supabase_teacher_review import SupabaseTeacherReviewStore, TeacherReviewPersistenceError
from agent.teacher_review import TeacherReviewStore
from shared.contracts import Activity

SECRET = "runtime-server-secret-marker"
URL = "https://offline.supabase.invalid"


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "NEXT_PUBLIC_SUPABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runtime, "REPO_ROOT", tmp_path)


@pytest.fixture
def client_factory(monkeypatch):
    client = MagicMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(runtime, "get_client", factory)
    return client, factory


def configure(tmp_path):
    (tmp_path / ".env").write_text(f"SUPABASE_URL={URL}\nSUPABASE_SERVICE_ROLE_KEY={SECRET}\n")


@pytest.mark.parametrize("source", ["root", "web", "process", "explicit_file"])
def test_runtime_uses_persistent_store_and_shared_factory(
    source, tmp_path, monkeypatch, client_factory
):
    client, factory = client_factory
    kwargs = {}
    if source == "root":
        configure(tmp_path)
    elif source == "web":
        (tmp_path / "web").mkdir()
        (tmp_path / "web/.env.local").write_text(
            f"NEXT_PUBLIC_SUPABASE_URL={URL}\nSUPABASE_SERVICE_ROLE_KEY={SECRET}\n"
        )
        monkeypatch.setenv("SUPABASE_URL", "")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    elif source == "process":
        monkeypatch.setenv("SUPABASE_URL", URL)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    else:
        path = tmp_path / "backend.env"
        path.write_text(f"SUPABASE_URL={URL}\nSUPABASE_SERVICE_ROLE_KEY={SECRET}\n")
        kwargs["env_file"] = path
    agent = runtime.create_runtime_agent(
        FakeMessagesListChatModel(responses=[]), ProgressHistoryStore(), **kwargs
    )
    assert isinstance(agent.reviews, SupabaseTeacherReviewStore)
    assert agent.reviews.client is client
    factory.assert_called_once_with(URL, SECRET)
    client.table.assert_called_once_with("teacher_reviews")
    client.table.return_value.select.assert_called_once_with("id")
    client.table.return_value.select.return_value.limit.assert_called_once_with(1)


def test_nonempty_process_config_wins_over_root_and_web(tmp_path, monkeypatch, client_factory):
    configure(tmp_path)
    (tmp_path / "web").mkdir()
    (tmp_path / "web/.env.local").write_text("SUPABASE_URL=https://other.invalid\n")
    monkeypatch.setenv("SUPABASE_URL", "https://process.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "process-secret")
    runtime.review_store_from_env()
    client_factory[1].assert_called_once_with("https://process.invalid", "process-secret")


def test_no_backend_config_remains_offline_even_with_frontend_url(tmp_path, client_factory):
    (tmp_path / ".env").write_text("NEXT_PUBLIC_SUPABASE_URL=https://public.invalid\n")
    assert isinstance(runtime.review_store_from_env(), TeacherReviewStore)
    client_factory[1].assert_not_called()


def test_explicit_offline_ignores_config_and_does_not_construct_client(tmp_path, client_factory):
    configure(tmp_path)
    agent = runtime.create_runtime_agent(
        FakeMessagesListChatModel(responses=[]), ProgressHistoryStore(), offline=True
    )
    assert isinstance(agent.reviews, TeacherReviewStore)
    client_factory[1].assert_not_called()


def test_continuous_runtime_reuses_persistent_client_for_seat_state(tmp_path, client_factory):
    configure(tmp_path)
    client = client_factory[0]
    result = runtime.create_seat_state_runtime(
        FakeMessagesListChatModel(responses=[]),
        [Activity(id="task", name="Task", check_type="rule", no_progress_seconds=30)],
    )
    assert result.source.client is client
    assert result.pipeline.agent.reviews.client is client


def test_continuous_runtime_accepts_explicit_offline_source(client_factory):
    source = MagicMock()
    source.fetch.return_value = []
    result = runtime.create_seat_state_runtime(
        FakeMessagesListChatModel(responses=[]),
        [Activity(id="task", name="Task", check_type="rule", no_progress_seconds=30)],
        source=source,
        offline=True,
    )
    assert result.source is source
    assert isinstance(result.pipeline.agent.reviews, TeacherReviewStore)
    client_factory[1].assert_not_called()


def test_continuous_runtime_without_source_or_backend_fails_clearly(client_factory):
    with pytest.raises(runtime.RuntimePersistenceError, match="SeatState runtime requires"):
        runtime.create_seat_state_runtime(
            FakeMessagesListChatModel(responses=[]),
            [Activity(id="task", name="Task", check_type="rule", no_progress_seconds=30)],
            offline=True,
        )
    client_factory[1].assert_not_called()


@pytest.mark.parametrize("entry", [f"SUPABASE_URL={URL}", f"SUPABASE_SERVICE_ROLE_KEY={SECRET}"])
def test_partial_configuration_never_falls_back(tmp_path, client_factory, entry):
    (tmp_path / ".env").write_text(entry)
    with pytest.raises(runtime.RuntimePersistenceError, match="Incomplete review persistence"):
        runtime.review_store_from_env()
    client_factory[1].assert_not_called()


def test_explicit_missing_env_file_fails_clearly(tmp_path, client_factory):
    with pytest.raises(runtime.RuntimePersistenceError, match="env file does not exist"):
        runtime.review_store_from_env(env_file=tmp_path / "missing.env")
    client_factory[1].assert_not_called()


@pytest.mark.parametrize("failure", ["constructor", "readiness"])
def test_initialization_failure_is_sanitized_and_does_not_fall_back(
    tmp_path, client_factory, caplog, failure
):
    configure(tmp_path)
    client, factory = client_factory
    if failure == "constructor":
        factory.side_effect = RuntimeError(SECRET)
    else:
        client.table.return_value.select.return_value.limit.return_value.execute.side_effect = (
            RuntimeError(SECRET)
        )
    with caplog.at_level(logging.INFO), pytest.raises(runtime.RuntimePersistenceError) as error:
        runtime.review_store_from_env()
    assert "No in-memory fallback" in str(error.value)
    assert SECRET not in str(error.value) + caplog.text
    assert error.value.__suppress_context__ is True


class ActionModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def action_model():
    return ActionModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "request_teacher_review",
                        "id": "review",
                        "args": {
                            "rationale": "Synthetic runtime wiring test.",
                            "evidence_used": ["current_progress"],
                        },
                    }
                ],
            )
        ]
    )


def context():
    return EnrichedEvaluationContext(
        AgentEvaluationRequest(
            UUID(int=1),
            "A",
            "task",
            datetime(2026, 11, 14, tzinfo=UTC),
            ProgressState("stalled", 30),
            EscalationDecision(True, "elevated", "prolonged_stalled_progress"),
        ),
        Activity(id="task", name="Raise hand", check_type="rule", no_progress_seconds=30),
    )


def test_write_failure_in_actual_action_path_does_not_create_memory_review(
    tmp_path, client_factory
):
    configure(tmp_path)
    client = client_factory[0]
    client.table.return_value.upsert.return_value.execute.side_effect = APIError(
        {"message": SECRET, "code": "503", "details": "", "hint": ""}
    )
    agent = runtime.create_runtime_agent(action_model(), ProgressHistoryStore())
    with pytest.raises(TeacherReviewPersistenceError):
        agent.run(context())
    assert isinstance(agent.reviews, SupabaseTeacherReviewStore)


def test_credentials_do_not_enter_context_or_structured_output(tmp_path, client_factory, caplog):
    from agent.deep_agent import serialize_agent_context
    from agent.supabase_teacher_review import review_to_row

    configure(tmp_path)
    client = client_factory[0]
    original = TeacherReviewStore().request_teacher_review(
        context().request,
        AgentAssessment(
            decision="teacher_review_warranted",
            rationale="Synthetic runtime wiring test.",
            evidence_used=["current_progress"],
        ),
    )
    # No open review yet for this person, so the store creates one.
    client.table.return_value.select.return_value.match.return_value.limit.return_value.execute.return_value.data = []  # noqa: E501
    client.table.return_value.upsert.return_value.execute.return_value.data = [
        review_to_row(original)
    ]
    with caplog.at_level(logging.INFO):
        agent = runtime.create_runtime_agent(action_model(), ProgressHistoryStore())
        result = agent.run(context())
    serialized = json.dumps(
        {
            "context": serialize_agent_context(context()),
            "assessment": result.assessment.model_dump(mode="json"),
            "review": result.pending_review.model_dump(mode="json"),
        }
    )
    assert SECRET not in serialized + caplog.text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in serialized
    assert result.pending_review.id == original.id
