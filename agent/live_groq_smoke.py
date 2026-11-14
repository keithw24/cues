"""Optional live evaluation: uv run python -m agent.live_groq_smoke.

Requires GROQ_API_KEY (environment or ignored root .env). Uses only synthetic data.
This script makes paid/rate-limited API calls; it is not collected by pytest.
Tool choices are observed, never forced. Inspect rationales against logged evidence.
Review actions use runtime-selected storage and persist when Supabase is configured.
Use --offline-reviews to explicitly retain review actions only in memory.
"""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq

from agent.context_enricher import ContextEnricher, EnrichedEvaluationContext
from agent.deep_agent import serialize_agent_context, validate_assessment
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.prompt_history import PromptHistoryEntry, PromptHistoryStore
from agent.router import AgentEvaluationRequest
from agent.runtime import create_runtime_agent
from shared.contracts import Activity, SeatState

MODEL = "openai/gpt-oss-20b"
SCENARIOS = (
    "current_context_sufficient",
    "ambiguous_stall",
    "repeated_stalls",
    "prompt_support_pattern",
    "mixed_ambiguous",
    "empty_history",
    "review_action",
    "prolonged_review_action",
)


def scenario(
    name: str,
    *,
    session_id: UUID | None = None,
    seat_id: str = "SIM-A",
    observed_at: datetime | None = None,
) -> tuple[EnrichedEvaluationContext, ProgressHistoryStore, PromptHistoryStore]:
    """Build independent synthetic current contexts and prior summary histories."""
    now = observed_at or datetime(2026, 11, 14, 2, 10, tzinfo=UTC)
    session = session_id if session_id is not None else UUID(int=1)
    activity = Activity(
        id="raise_hand", name="Raise your hand", check_type="rule", no_progress_seconds=30
    )
    sufficient = name == "current_context_sufficient"
    prolonged = name == "prolonged_review_action"
    request = AgentEvaluationRequest(
        session,
        seat_id,
        activity.id,
        now,
        ProgressState(
            "improving" if sufficient else "stalled", 0 if sufficient else 30 if prolonged else 10
        ),
        EscalationDecision(False)
        if sufficient
        else EscalationDecision(True, "elevated", "prolonged_stalled_progress")
        if prolonged
        else EscalationDecision(True, "normal", "stalled_progress"),
    )
    # Direct assessment of a recovered request tests monitoring; this intentionally
    # bypasses router eligibility and is not a change to routing behavior.
    store = ProgressHistoryStore()
    summaries = {
        "current_context_sufficient": [],
        "ambiguous_stall": [("improving", 0), ("completed", 0)],
        "repeated_stalls": [
            ("stalled", 12),
            ("improving", 0),
            ("stalled", 14),
            ("improving", 0),
            ("stalled", 16),
        ],
        "prompt_support_pattern": [("unknown", 0)],
        "mixed_ambiguous": [("stalled", 12), ("improving", 0)],
        "empty_history": [],
        "prolonged_review_action": [("stalled", 25), ("stalled", 30), ("stalled", 35)],
    }["repeated_stalls" if name == "review_action" else name]
    for i, (trend, seconds) in enumerate(summaries):
        snapshot = SeatState(
            session_id=session,
            seat_id=request.seat_id,
            activity_id=activity.id,
            status="done" if trend == "completed" else "in_progress",
            tracking_valid=True,
            updated_at=now - timedelta(seconds=(len(summaries) - i) * (40 if prolonged else 20)),
        )
        store.record(snapshot, ProgressState(trend, seconds))
    prompts = PromptHistoryStore()
    outcomes = {
        "prompt_support_pattern": [
            "independent_correct",
            "prompted_correct",
            "prompted_correct",
            "prompted_correct",
        ],
        "mixed_ambiguous": ["independent_correct", "incorrect", "prompted_correct", "no_response"],
        "prolonged_review_action": ["prompted_correct", "prompted_correct", "no_response"],
    }.get(name, [])
    for i, outcome in enumerate(outcomes):
        prompts.record(
            session,
            request.seat_id,
            activity.id,
            PromptHistoryEntry(
                observed_at=now - timedelta(seconds=(len(outcomes) - i) * 20), outcome=outcome
            ),
        )
    return ContextEnricher([activity]).enrich(request), store, prompts


def evaluate(name: str, model: ChatGroq, *, offline_reviews: bool = False) -> dict:
    context, store, prompts = scenario(
        name, session_id=uuid4(), seat_id="S1-L", observed_at=datetime.now(UTC)
    )
    payload = serialize_agent_context(context)
    # Evaluation questions distinguish the requested assessment, not which tools
    # must be called. No stored outcomes are revealed in the question.
    question = {
        "prolonged_review_action": (
            "Assess this prolonged eligible stall in light of recent task progress and "
            "observed support outcomes. Decide whether teacher attention is useful and "
            "whether to create a pending review. Retrieve information only if it materially "
            "helps your decision."
        ),
        "review_action": (
            "Assess whether the observed progress pattern warrants teacher attention. "
            "If useful, decide whether to create a pending review for the teacher."
        ),
        "ambiguous_stall": (
            "Assess whether recent observed task-progress trends show recovery around this stall."
        ),
        "repeated_stalls": (
            "Assess whether observed task-progress history shows a recurring stall pattern."
        ),
        "empty_history": (
            "Assess this stall using whatever recent progress or independence "
            "history is available; acknowledge missing observations."
        ),
        "prompt_support_pattern": (
            "Assess whether recent observed independent versus prompted "
            "responses suggest changing support needs for this task."
        ),
        "mixed_ambiguous": (
            "Assess whether the recent progress pattern and observed "
            "independence/support outcomes together warrant teacher review."
        ),
    }.get(name)
    model_input = (
        payload
        if question is None
        else json.dumps({"context": json.loads(payload), "assessment_question": question})
    )
    report = {
        "scenario": name,
        "tools_called": [],
        "evidence_repair_attempted": False,
        "tool_results": [],
        "decision": None,
        "rationale": None,
        "same_run_followup": False,
        "post_action_model_turn": False,
        "pending_review": None,
        "input": json.loads(model_input),
    }
    print(f"\nScenario: {name}", flush=True)
    agent = create_runtime_agent(model, store, prompt_history=prompts, offline=offline_reviews)
    reviews = agent.reviews
    report["review_storage"] = type(reviews).__name__
    graph = agent.build(context)
    final = None
    try:
        # Observe the normal graph with no tool_choice override or prescribed sequence.
        for state in graph.stream(
            {"messages": [{"role": "user", "content": model_input}]},
            config=agent.run_config,
            stream_mode="values",
        ):
            final = state
        assessment = validate_assessment(final)
        report.update(assessment.model_dump())
        if review := final.get("pending_review"):
            report["pending_review"] = review.model_dump(mode="json")
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    if final is not None:
        report["evidence_repair_attempted"] = final.get("evidence_repair_attempted", False)
        messages = final.get("messages", [])
        for index, message in enumerate(messages):
            if isinstance(message, ToolMessage) and message.name in (
                "get_recent_progress_history",
                "get_prompt_history",
                "request_teacher_review",
            ):
                report["tools_called"].append(message.name)
                report["tool_results"].append(
                    dict(tool=message.name, status=message.status, content=message.content)
                )
                report["same_run_followup"] |= any(
                    isinstance(m, AIMessage) for m in messages[index + 1 :]
                )
                if message.name == "request_teacher_review" and message.status == "success":
                    report["post_action_model_turn"] |= any(
                        isinstance(m, AIMessage) for m in messages[index + 1 :]
                    )
    report["review_action_called"] = "request_teacher_review" in report["tools_called"]
    # Scope logging to this synthetic evaluation; never dump other stored reviews.
    pending = [r for r in reviews.get_pending_reviews() if r.evaluation == context.request]
    report["created_reviews"] = [r.model_dump(mode="json") for r in pending]
    report["created_review_context_verified"] = bool(pending) and all(
        r.evaluation == context.request and r.status == "pending" for r in pending
    )
    if pending and "error_type" not in report:
        # A successful action must terminate with the exact stored assessment/review.
        if (
            final.get("pending_review") != pending[0]
            or assessment != pending[0].assessment
            or report["post_action_model_turn"]
            or not report["created_review_context_verified"]
        ):
            report["error_type"] = "TerminalReviewValidationError"
    report["review_required"] = (
        "Check rationale against current context and tool results; "
        "no automatic hallucination judge."
    )
    print(json.dumps(report, indent=2), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument(
        "--offline-reviews",
        action="store_true",
        help="Explicitly keep review actions in memory even if Supabase is configured.",
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        action="append",
        help="Rerun selected scenarios; default runs all eight.",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    if not os.environ.get("GROQ_API_KEY"):
        print("Live evaluation not run: set GROQ_API_KEY locally; never paste or commit it.")
        return 2
    model = ChatGroq(model=args.model, temperature=0, max_retries=2, timeout=20)
    reports = [
        evaluate(name, model, offline_reviews=args.offline_reviews)
        for name in (args.scenario or SCENARIOS)
    ]
    exercised = {
        tool["tool"]
        for r in reports
        if "error_type" not in r and r["same_run_followup"]
        for tool in r["tool_results"]
        if tool["status"] == "success"
    }
    missing = sorted({"get_recent_progress_history", "get_prompt_history"} - exercised)
    print(
        json.dumps(
            {
                "model": args.model,
                "unexercised_tools": missing,
                "manual_evidence_review_required": True,
            },
            indent=2,
        )
    )
    return int(bool(missing) or any("error_type" in r for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
