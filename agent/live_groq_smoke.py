"""Optional live evaluation: uv run python -m agent.live_groq_smoke.

Requires GROQ_API_KEY (environment or ignored root .env). Uses only synthetic data.
This script makes paid/rate-limited API calls; it is not collected by pytest.
Tool choices are observed, never forced. Inspect rationales against logged evidence.
"""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq

from agent.context_enricher import ContextEnricher, EnrichedEvaluationContext
from agent.deep_agent import create_cues_deep_agent, serialize_agent_context, validate_assessment
from agent.escalation import EscalationDecision
from agent.progress import ProgressState
from agent.progress_history import ProgressHistoryStore
from agent.prompt_history import PromptHistoryEntry, PromptHistoryStore
from agent.router import AgentEvaluationRequest
from shared.contracts import Activity, SeatState

MODEL = "openai/gpt-oss-20b"
SCENARIOS = (
    "current_context_sufficient",
    "ambiguous_stall",
    "repeated_stalls",
    "prompt_support_pattern",
    "mixed_ambiguous",
    "empty_history",
)


def scenario(
    name: str,
) -> tuple[EnrichedEvaluationContext, ProgressHistoryStore, PromptHistoryStore]:
    """Build independent synthetic current contexts and prior summary histories."""
    now = datetime(2026, 11, 14, 2, 10, tzinfo=UTC)
    session = UUID(int=1)
    activity = Activity(
        id="raise_hand", name="Raise your hand", check_type="rule", no_progress_seconds=30
    )
    sufficient = name == "current_context_sufficient"
    request = AgentEvaluationRequest(
        session,
        "SIM-A",
        activity.id,
        now,
        ProgressState("improving" if sufficient else "stalled", 0 if sufficient else 10),
        EscalationDecision(False)
        if sufficient
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
    }[name]
    for i, (trend, seconds) in enumerate(summaries):
        snapshot = SeatState(
            session_id=session,
            seat_id=request.seat_id,
            activity_id=activity.id,
            status="done" if trend == "completed" else "in_progress",
            tracking_valid=True,
            updated_at=now - timedelta(seconds=(len(summaries) - i) * 20),
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


def evaluate(name: str, model: ChatGroq) -> dict:
    context, store, prompts = scenario(name)
    payload = serialize_agent_context(context)
    # Evaluation questions distinguish the requested assessment, not which tools
    # must be called. No stored outcomes are revealed in the question.
    question = {
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
        "tool_results": [],
        "decision": None,
        "rationale": None,
        "same_run_followup": False,
        "input": json.loads(model_input),
    }
    print(f"\nScenario: {name}", flush=True)
    agent = create_cues_deep_agent(model, store, prompt_history=prompts)
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
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    if final is not None:
        messages = final.get("messages", [])
        for index, message in enumerate(messages):
            if isinstance(message, ToolMessage) and message.name in (
                "get_recent_progress_history",
                "get_prompt_history",
            ):
                report["tools_called"].append(message.name)
                report["tool_results"].append(
                    dict(tool=message.name, status=message.status, content=message.content)
                )
                report["same_run_followup"] |= any(
                    isinstance(m, AIMessage) for m in messages[index + 1 :]
                )
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
        "--scenario",
        choices=SCENARIOS,
        action="append",
        help="Rerun selected scenarios; default runs all six.",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    if not os.environ.get("GROQ_API_KEY"):
        print("Live evaluation not run: set GROQ_API_KEY locally; never paste or commit it.")
        return 2
    model = ChatGroq(model=args.model, temperature=0, max_retries=2, timeout=20)
    reports = [evaluate(name, model) for name in (args.scenario or SCENARIOS)]
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
