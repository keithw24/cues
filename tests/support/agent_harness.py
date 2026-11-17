"""The one thing the agent tests replace: the language model.

Everything else in the agent is real (progress evaluation, escalation, routing, the Deep
Agent harness, the review store). The stand-in model asks for a teacher review the way the
real one does, can be taken down to simulate an outage, and keeps what it was asked so a test
can check what the model was and was not given.
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import Field


class StubModel(FakeMessagesListChatModel):
    calls: int = 0
    down: bool = False
    asked: list = Field(default_factory=list)  # (message type, text) of everything it was sent

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        self.asked.extend((message.type, str(message.content)) for message in messages)
        if self.down:
            raise RuntimeError("the model service is unreachable")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def shown_to_the_model(self) -> str:
        """What the task handed the model (the system prompt excluded)."""
        return "\n".join(text for kind, text in self.asked if kind != "system")


def review_call(suggestion: str | None = "show_example") -> AIMessage:
    """The model's answer: request a teacher review, citing only what it was given."""
    args = {
        "rationale": "The child has not progressed on the task.",
        "evidence_used": ["current_progress"],
    }
    if suggestion:
        args["suggested_intervention"] = suggestion
    return AIMessage(
        content="",
        tool_calls=[{"id": "review", "name": "request_teacher_review", "args": args}],
    )


def catalog():
    """The activities vision can run, as the shared contract the agent reads them in."""
    from shared.contracts import Activity
    from vision.activities import load_activities

    return [
        Activity(
            id=a.id,
            name=a.name,
            check_type=a.check_type,
            no_progress_seconds=a.no_progress_seconds,
            success_threshold=a.success_threshold,
            review_threshold=a.review_threshold,
        )
        for a in load_activities().values()
    ]
