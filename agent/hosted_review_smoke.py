"""Optional: uv run python -m agent.hosted_review_smoke.

Uses configured Supabase credentials and a scripted, tool-capable test model.
Exercises the real runtime/agent/action path without a paid LLM call. Creates one
synthetic pending review, verifies retrieval, then deletes only that probe row.
Never collected by pytest; no dashboard/session lifecycle is implemented here.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agent.context_enricher import ContextEnricher
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.router import AgentEvaluationRequest
from agent.runtime import create_runtime_agent
from agent.supabase_teacher_review import SupabaseTeacherReviewStore
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT

RATIONALE = "Synthetic runtime persistence verification."


class _ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def run_smoke(*, env_file: Path | None = None) -> dict:
    report = {"model": "scripted (no live LLM)", "checks": {}}
    agent = None
    context = None
    result = None
    try:
        model = _ScriptedModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_teacher_review",
                            "id": "review",
                            "args": {"rationale": RATIONALE, "evidence_used": ["current_progress"]},
                        }
                    ],
                )
            ]
        )
        agent = create_runtime_agent(model, ProgressHistoryStore(), env_file=env_file)
        if not isinstance(agent.reviews, SupabaseTeacherReviewStore):
            raise RuntimeError("Hosted verification requires Supabase persistence")
        report["review_storage"] = type(agent.reviews).__name__
        activities = [
            Activity.model_validate(row)
            for row in json.loads((REPO_ROOT / "shared/fixtures/activities.json").read_text())
        ]
        context = ContextEnricher(activities).enrich(
            AgentEvaluationRequest(
                uuid4(),
                "S1-L",
                "raise_hand",
                datetime.now(UTC),
                ProgressState("stalled", 30),
                EscalationDecision(True, "elevated", "prolonged_stalled_progress"),
            )
        )
        result = agent.run(context)
        review = result.pending_review
        assert review is not None and review.status == "pending"
        assert review.evaluation == context.request
        assert result.assessment == review.assessment
        assert agent.reviews.get_review(review.id) == review
        assert review.id in [r.id for r in agent.reviews.get_pending_reviews()]
        restarted_store = SupabaseTeacherReviewStore(agent.reviews.client)
        assert restarted_store.get_review(review.id) == review
        report.update(review_id=str(review.id), status=review.status)
        report["checks"].update(
            runtime_selected_supabase=True,
            actual_action_created_review=True,
            retrieved_pending=True,
            trusted_context_preserved=True,
            separate_store_retrieved=True,
        )
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        if agent is not None and context is not None:
            try:
                # Unique probe session and rationale scope cleanup even if a
                # response was lost after a successful database commit.
                deleted = (
                    agent.reviews.client.table("teacher_reviews")
                    .delete()
                    .eq("session_id", str(context.request.session_id))
                    .eq("rationale", RATIONALE)
                    .execute()
                    .data
                )
                remaining = (
                    agent.reviews.client.table("teacher_reviews")
                    .select("id")
                    .eq("session_id", str(context.request.session_id))
                    .execute()
                    .data
                )
                assert not remaining
                report["cleanup_deleted"] = len(deleted)
                report["checks"]["probe_cleaned_up"] = True
            except Exception as error:
                report["cleanup_error_type"] = type(error).__name__
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Use a specific backend env file.")
    args = parser.parse_args()
    report = run_smoke(env_file=args.env_file)
    print(json.dumps(report, indent=2))
    return int("error_type" in report or "cleanup_error_type" in report)


if __name__ == "__main__":
    raise SystemExit(main())
