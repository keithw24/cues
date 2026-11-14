"""Real Supabase SDK against an HTTP fake: no credentials or network required."""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from supabase.lib.client_options import SyncClientOptions

from agent.assessment import AgentAssessment
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.router import AgentEvaluationRequest
from agent.supabase_teacher_review import (
    SupabaseTeacherReviewStore,
    TeacherReviewPersistenceError,
    review_from_row,
    review_to_row,
)
from agent.teacher_review import TeacherReviewStore
from supabase import create_client

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def evaluation(**changes):
    return replace(
        AgentEvaluationRequest(
            UUID(int=1),
            "A",
            "task",
            NOW,
            ProgressState("stalled", 30),
            EscalationDecision(True, "elevated", "prolonged_stalled_progress"),
        ),
        **changes,
    )


def assessment():
    return AgentAssessment(
        decision="teacher_review_warranted",
        rationale="Repeated prolonged stalls warrant review.",
        evidence_used=["current_progress", "recent_progress_history"],
    )


class ReviewDatabase:
    """Small PostgREST fake with shared rows, conflict handling and conditional updates."""

    def __init__(self):
        self.rows = []
        self.calls = []
        self.fail_method = None
        self.resolve_race = False
        self.page_cap = 2  # Exercise pagination despite a lower server row cap.

    def __call__(self, request):
        assert request.url.path.endswith("/teacher_reviews")
        self.calls.append(request)
        if request.method == self.fail_method:
            return httpx.Response(503, json={"message": "private server detail", "code": "503"})
        params = request.url.params
        if request.method == "POST":
            row = json.loads(request.content)
            assert params["on_conflict"] == "evaluation"
            assert "resolution=ignore-duplicates" in request.headers["prefer"]
            if any(r["evaluation"] == row["evaluation"] for r in self.rows):
                return httpx.Response(201, json=[])
            self.rows.append(row)
            return httpx.Response(201, json=[row])
        rows = list(self.rows)
        for key in ("id", "status", "evaluation", "session_id", "rationale"):
            if key in params:
                value = params[key].removeprefix("eq.")
                if key == "evaluation":
                    value = json.loads(value)
                rows = [row for row in rows if row[key] == value]
        if request.method == "DELETE":
            removed_ids = {row["id"] for row in rows}
            self.rows = [row for row in self.rows if row["id"] not in removed_ids]
            return httpx.Response(200, json=rows)
        if request.method == "PATCH":
            if self.resolve_race:
                self.resolve_race = False
                for row in rows:
                    row.update(status="dismissed", resolved_at=NOW.isoformat())
                return httpx.Response(200, json=[])
            update = json.loads(request.content)
            assert set(update) == {"status", "resolved_at"}
            assert params["status"] == "eq.pending"
            for row in rows:
                row.update(update)
            return httpx.Response(200, json=rows)
        assert request.method == "GET"
        if "order" in params:
            assert params["order"] == "created_at.asc,id.asc"
            rows.sort(key=lambda row: (row["created_at"], row["id"]))
        offset = int(params.get("offset", 0))
        limit = min(int(params.get("limit", self.page_cap)), self.page_cap)
        return httpx.Response(200, json=rows[offset : offset + limit])


@pytest.fixture
def database():
    fake = ReviewDatabase()
    with httpx.Client(
        base_url="https://supabase.invalid/rest/v1/", transport=httpx.MockTransport(fake)
    ) as http:
        client = create_client(
            "https://supabase.invalid",
            "offline-test-key",
            options=SyncClientOptions(
                httpx_client=http,
                auto_refresh_token=False,
                persist_session=False,
                postgrest_client_retry=False,
            ),
        )
        yield fake, client


def test_row_round_trip_preserves_typed_context_evidence_and_exact_times():
    review = TeacherReviewStore(clock=lambda: NOW).request_teacher_review(
        evaluation(), assessment()
    )
    row = review_to_row(review)
    assert row["session_id"] == str(UUID(int=1))
    assert row["seat_id"] == "A" and row["activity_id"] == "task"
    assert row["priority"] == "elevated" and row["decision"] == "teacher_review_warranted"
    assert row["evidence_used"] == ["current_progress", "recent_progress_history"]
    assert review_from_row(json.loads(json.dumps(row))) == review


def test_create_survives_adapter_restart_and_equivalent_timezone_offset(database):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    review = store.request_teacher_review(evaluation(), assessment())
    restarted = SupabaseTeacherReviewStore(client, clock=lambda: NOW + timedelta(seconds=5))
    assert restarted.get_review(review.id) == review
    equivalent = evaluation(observed_at=NOW.astimezone(timezone(timedelta(hours=5))))
    changed = assessment().model_copy(update={"rationale": "A later rationale must not overwrite."})
    assert restarted.request_teacher_review(equivalent, changed) == review
    assert len(db.rows) == 1


def test_pending_retrieval_pages_and_orders_results(database):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    reviews = [
        store.request_teacher_review(evaluation(seat_id=str(i)), assessment()) for i in range(5)
    ]
    assert len(db.rows) > db.page_cap
    assert store.get_pending_reviews() == sorted(reviews, key=lambda r: (r.created_at, str(r.id)))
    assert SupabaseTeacherReviewStore(client).get_pending_reviews() == store.get_pending_reviews()


@pytest.mark.parametrize(
    ("method", "status"),
    [("confirm_needs_attention", "confirmed"), ("dismiss_review", "dismissed")],
)
def test_resolution_updates_only_status_and_time_and_excludes_pending(database, method, status):
    db, client = database
    times = iter([NOW, NOW + timedelta(seconds=5)])
    store = SupabaseTeacherReviewStore(client, clock=lambda: next(times))
    original = store.request_teacher_review(evaluation(), assessment())
    before = copy.deepcopy(db.rows[0])
    resolved = getattr(store, method)(original.id)
    assert resolved.status == status and resolved.resolved_at == NOW + timedelta(seconds=5)
    assert resolved.evaluation == original.evaluation and resolved.assessment == original.assessment
    assert {k: v for k, v in db.rows[0].items() if k not in ("status", "resolved_at")} == {
        k: v for k, v in before.items() if k not in ("status", "resolved_at")
    }
    assert store.get_pending_reviews() == []
    assert SupabaseTeacherReviewStore(client).get_review(original.id) == resolved


@pytest.mark.parametrize("method", ["get_review", "confirm_needs_attention", "dismiss_review"])
def test_unknown_id(database, method):
    _, client = database
    with pytest.raises(KeyError, match="unknown review ID"):
        getattr(SupabaseTeacherReviewStore(client), method)(UUID(int=0))


@pytest.mark.parametrize("first", ["confirm_needs_attention", "dismiss_review"])
@pytest.mark.parametrize("second", ["confirm_needs_attention", "dismiss_review"])
def test_repeated_resolution_and_reopening_fail_without_overwriting(database, first, second):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    review = store.request_teacher_review(evaluation(), assessment())
    resolved = getattr(store, first)(review.id)
    before = copy.deepcopy(db.rows)
    with pytest.raises(ValueError, match="already resolved"):
        getattr(store, second)(review.id)
    with pytest.raises(ValueError, match="already resolved"):
        store.request_teacher_review(evaluation(), assessment())
    assert store.get_review(review.id) == resolved and db.rows == before


def test_concurrent_resolution_uses_pending_condition(database):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    review = store.request_teacher_review(evaluation(), assessment())
    db.resolve_race = True
    with pytest.raises(ValueError, match="already resolved"):
        store.confirm_needs_attention(review.id)
    assert store.get_review(review.id).status == "dismissed"


@pytest.mark.parametrize("operation", ["create", "get", "pending", "resolve"])
def test_database_failures_raise_without_memory_fallback(database, operation):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    review = store.request_teacher_review(evaluation(), assessment())
    before = copy.deepcopy(db.rows)
    db.fail_method = {"create": "POST", "get": "GET", "pending": "GET", "resolve": "PATCH"}[
        operation
    ]
    actions = {
        "create": lambda: store.request_teacher_review(evaluation(seat_id="B"), assessment()),
        "get": lambda: store.get_review(review.id),
        "pending": store.get_pending_reviews,
        "resolve": lambda: store.dismiss_review(review.id),
    }
    with pytest.raises(TeacherReviewPersistenceError, match="operation failed") as error:
        actions[operation]()
    assert "private server detail" not in str(error.value)
    assert db.rows == before


def test_network_failure_is_not_an_empty_pending_list():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(
        base_url="https://supabase.invalid/rest/v1/", transport=httpx.MockTransport(fail)
    ) as http:
        client = create_client(
            "https://supabase.invalid",
            "offline-test-key",
            options=SyncClientOptions(httpx_client=http, postgrest_client_retry=False),
        )
        with pytest.raises(TeacherReviewPersistenceError):
            SupabaseTeacherReviewStore(client).get_pending_reviews()


@pytest.mark.parametrize(
    "changes", [{"evidence_used": ["invented"]}, {"seat_id": "OTHER"}, {"created_at": "2026-11-14"}]
)
def test_malformed_or_inconsistent_rows_are_rejected(database, changes):
    db, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    review = store.request_teacher_review(evaluation(), assessment())
    db.rows[0].update(changes)
    with pytest.raises(TeacherReviewPersistenceError, match="invalid review data"):
        store.get_review(review.id)


def test_invalid_request_never_reaches_supabase(database):
    db, client = database
    store = SupabaseTeacherReviewStore(client)
    with pytest.raises(ValueError, match="eligible stalled"):
        store.request_teacher_review(evaluation(progress=ProgressState("completed")), assessment())
    assert not db.calls


@pytest.mark.parametrize("entrypoint", ["core", "runtime", "live_runner"])
def test_existing_deep_agent_can_use_persistent_store_without_another_node(
    database, entrypoint, monkeypatch, tmp_path
):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from agent import runtime
    from agent.context_enricher import EnrichedEvaluationContext
    from agent.deep_agent import create_cues_deep_agent
    from agent.progress_history import ProgressHistoryStore
    from shared.contracts import Activity

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    _, client = database
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW)
    if entrypoint != "core":
        for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "NEXT_PUBLIC_SUPABASE_URL"):
            monkeypatch.delenv(key, raising=False)
        (tmp_path / ".env").write_text(
            "SUPABASE_URL=https://supabase.invalid\nSUPABASE_SERVICE_ROLE_KEY=offline-test-key\n"
        )
        monkeypatch.setattr(runtime, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(runtime, "get_client", lambda url, key: client)
    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "review",
                        "name": "request_teacher_review",
                        "args": {
                            "rationale": "The current prolonged stall warrants review.",
                            "evidence_used": ["current_progress"],
                        },
                    }
                ],
            )
        ]
    )
    context = EnrichedEvaluationContext(
        evaluation(),
        Activity(id="task", name="Raise hand", check_type="rule", no_progress_seconds=30),
    )
    if entrypoint == "live_runner":
        from agent.live_groq_smoke import evaluate

        report = evaluate("prolonged_review_action", model)
        assert report["review_storage"] == "SupabaseTeacherReviewStore"
        assert report["review_action_called"] and report["created_review_context_verified"]
        assert "error_type" not in report
        assert store.get_review(UUID(report["pending_review"]["id"])).status == "pending"
        return
    agent = (
        runtime.create_runtime_agent(model, ProgressHistoryStore())
        if entrypoint == "runtime"
        else create_cues_deep_agent(model, ProgressHistoryStore(), reviews=store)
    )
    result = agent.run(context)
    assert result.pending_review.status == "pending"
    assert result.assessment == result.pending_review.assessment
    assert SupabaseTeacherReviewStore(client).get_review(result.pending_review.id) == (
        result.pending_review
    )


@pytest.mark.parametrize("fail_write", [False, True])
def test_hosted_smoke_uses_runtime_and_cleans_only_its_probe(
    database, monkeypatch, tmp_path, fail_write
):
    from agent import runtime
    from agent.hosted_review_smoke import run_smoke

    db, client = database
    unrelated = SupabaseTeacherReviewStore(client, clock=lambda: NOW).request_teacher_review(
        evaluation(), assessment()
    )
    for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "NEXT_PUBLIC_SUPABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "SUPABASE_URL=https://supabase.invalid\nSUPABASE_SERVICE_ROLE_KEY=offline-test-key\n"
    )
    monkeypatch.setattr(runtime, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runtime, "get_client", lambda url, key: client)
    if fail_write:
        db.fail_method = "POST"
    report = run_smoke()
    assert report["review_storage"] == "SupabaseTeacherReviewStore"
    assert report["checks"]["probe_cleaned_up"] is True
    assert report["cleanup_deleted"] == (0 if fail_write else 1)
    if fail_write:
        assert report["error_type"] == "TeacherReviewPersistenceError"
    else:
        assert "error_type" not in report and report["checks"]["actual_action_created_review"]
    assert [row["id"] for row in db.rows] == [str(unrelated.id)]


@pytest.mark.parametrize("delivery_failure", [False, True])
@pytest.mark.parametrize("resolution", ["confirm_needs_attention", "dismiss_review"])
def test_new_persisted_review_notifies_once_without_changing_review(
    database, delivery_failure, caplog, resolution
):
    from agent.notifications import PhotonNotifier

    calls = []

    def send(message, review_id):
        calls.append((message, review_id))
        if delivery_failure:
            raise RuntimeError("private provider detail")

    db, client = database
    notifier = PhotonNotifier(send)
    store = SupabaseTeacherReviewStore(client, clock=lambda: NOW, notifier=notifier)
    review = store.request_teacher_review(evaluation(), assessment())
    assert store.get_review(review.id) == review
    assert store.request_teacher_review(evaluation(), assessment()) == review
    other_process = SupabaseTeacherReviewStore(client, notifier=notifier)
    assert other_process.request_teacher_review(evaluation(), assessment()) == review
    assert calls == [("Cues: Seat A may need attention. Open Cues to review.", str(review.id))]
    assert review.assessment.rationale not in calls[0][0]
    getattr(store, resolution)(review.id)
    assert len(calls) == 1
    if delivery_failure:
        assert "pending review retained" in caplog.text
        assert "private provider detail" not in caplog.text


def test_failed_persistence_does_not_notify(database):
    from unittest.mock import Mock

    db, client = database
    notifier = Mock()
    db.fail_method = "POST"
    store = SupabaseTeacherReviewStore(client, notifier=notifier)
    with pytest.raises(TeacherReviewPersistenceError):
        store.request_teacher_review(evaluation(), assessment())
    notifier.notify_pending_review.assert_not_called()
