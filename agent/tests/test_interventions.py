"""Intervention workflow: an approved menu, a suggestion only, flag-gated (PRD 12, 13, 26)."""

import json
import re
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from agent.assessment import AgentAssessment
from agent.deep_agent import _system_prompt, create_cues_deep_agent
from agent.progress_history import ProgressHistoryStore
from agent.supabase_teacher_review import review_from_row, review_to_row
from agent.teacher_review import TeacherReviewStore
from agent.tests.test_deep_agent import ToolModel, context
from shared.contracts import INTERVENTION_MENU

ROOT = Path(__file__).resolve().parents[2]


def call(**extra):
    return AIMessage(
        content="",
        tool_calls=[
            dict(
                name="request_teacher_review",
                id="review",
                args=dict(
                    rationale="Repeated observed stalls merit teacher review.",
                    evidence_used=["current_progress"],
                    **extra,
                ),
            )
        ],
    )


def run(monkeypatch, flag, **extra):
    monkeypatch.setenv("CUES_FLAG_AGENT_INTERVENTIONS", flag)
    reviews = TeacherReviewStore()
    create_cues_deep_agent(
        ToolModel(responses=[call(**extra)]), ProgressHistoryStore(), reviews=reviews
    ).run(context())
    (review,) = reviews.get_pending_reviews()
    return review


def test_menu_is_the_same_in_python_sql_and_web():
    keys = set(INTERVENTION_MENU)
    sql = (ROOT / "supabase/migrations/20261114001800_interventions.sql").read_text()
    lists = [
        tuple(sorted(re.findall(r"'([a-z_]+)'", m))) for m in re.findall(r"in \(([^)]*)\)", sql)
    ]
    in_sql = {entry for entry in lists if "offer_break" in entry}
    assert in_sql == {tuple(sorted(keys))}
    web = (ROOT / "web/lib/interventions.ts").read_text()
    assert (
        set(re.findall(r'^\s*(\w+):\s*"', web.split("export const INTERVENTION_MENU")[1], re.M))
        >= keys
    )


def test_menu_wording_never_names_a_childs_state():
    for label in INTERVENTION_MENU.values():
        assert not re.search(r"anxious|upset|angry|sad|frustrat|diagnos|disorder", label, re.I)


def test_only_menu_items_are_accepted():
    kwargs = dict(decision="teacher_review_warranted", rationale="r", evidence_used=["activity"])
    assert AgentAssessment(**kwargs).suggested_intervention is None
    assert AgentAssessment(**kwargs, suggested_intervention="offer_break")
    with pytest.raises(ValidationError):
        AgentAssessment(**kwargs, suggested_intervention="change_the_task")


def test_flag_off_drops_the_suggestion(monkeypatch):
    review = run(monkeypatch, "0", suggested_intervention="offer_break")
    assert review.assessment.suggested_intervention is None
    assert "offer_break" not in _system_prompt()


def test_flag_on_keeps_a_menu_suggestion_and_lists_the_menu(monkeypatch):
    review = run(monkeypatch, "1", suggested_intervention="show_example")
    assert review.assessment.suggested_intervention == "show_example"
    assert review.status == "pending"  # a suggestion changes nothing by itself
    prompt = _system_prompt()
    assert all(key in prompt for key in INTERVENTION_MENU)
    assert "teacher" in prompt


def test_row_carries_the_suggestion_only_when_there_is_one(monkeypatch):
    plain = run(monkeypatch, "1")
    assert "suggested_intervention" not in review_to_row(plain)
    suggested = run(monkeypatch, "1", suggested_intervention="adult_check_in")
    row = json.loads(json.dumps(review_to_row(suggested)))
    assert row["suggested_intervention"] == "adult_check_in"
    assert review_from_row(row) == suggested
    # A row from a database without the column still reads.
    del row["suggested_intervention"]
    assert review_from_row(row).assessment.suggested_intervention is None
