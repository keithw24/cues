"""Optional hosted SeatState -> review -> Photon integration smoke."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dotenv import dotenv_values
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agent.escalation import DEMO_ESCALATION_CONFIG
from agent.notifications import spectrum_notifier
from agent.runtime import create_seat_state_runtime
from agent.seat_state_runtime import SupabaseSeatStateSource
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT
from vision.events import SupabaseSink


class ActionModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class ScopedSource(SupabaseSeatStateSource):
    def __init__(self, client, seat_id):
        super().__init__(client)
        self.seat_id = seat_id

    def fetch(self):
        response = (
            self.client.table("seat_state")
            .select(self.FIELDS)
            .eq("seat_id", self.seat_id)
            .execute()
        )
        return response.data or []


class ObservedNotifier:
    def __init__(self, inner):
        self.inner = inner
        self.attempts = 0
        self.acknowledged = False

    def notify_pending_review(self, review):
        self.attempts += 1
        self.inner.notify_pending_review(review)
        self.acknowledged = True


def main() -> None:
    spectrum = {
        k: v
        for k, v in dotenv_values(REPO_ROOT / "cues/.env").items()
        if k.startswith("SPECTRUM_") and v
    }
    notifier = spectrum_notifier(spectrum, REPO_ROOT)
    if notifier is None:
        raise RuntimeError("Spectrum backend configuration is unavailable")
    observed = ObservedNotifier(notifier)
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
    activity = Activity(
        id="raise_hand", name="Raise your hand", check_type="rule", no_progress_seconds=30
    )
    runtime = create_seat_state_runtime(
        model,
        [activity],
        notifier=observed,
        progress_window_seconds=2,
        escalation_config=DEMO_ESCALATION_CONFIG,
    )
    client = runtime.pipeline.agent.reviews.client
    seat_id = f"SMOKE-{uuid4()}"
    session_id = str(uuid4())
    runtime.source = ScopedSource(client, seat_id)
    sink = SupabaseSink(client)
    base = datetime.now(UTC).replace(microsecond=0)
    review = None
    try:
        for seconds in range(5):
            observed_at = base + timedelta(seconds=seconds)
            sink.write_seat_state(
                {
                    "seat_id": seat_id,
                    "session_id": session_id,
                    "activity_id": activity.id,
                    "status": "in_progress",
                    "updated_at": observed_at.isoformat(),
                    "tracking_valid": True,
                    "task_score": None,
                    "expression_context": None,
                }
            )
            runtime.pipeline.clock = lambda value=observed_at: value
            for result in runtime.run_once():
                if result.agent_result is not None:
                    review = result.agent_result.pending_review
        if review is None:
            raise RuntimeError("synthetic stalled sequence did not create a review")
        stored = client.table("teacher_reviews").select("*").eq("id", str(review.id)).execute().data
        print(
            json.dumps(
                {
                    "review_persisted_pending": bool(stored and stored[0]["status"] == "pending"),
                    "photon_attempts": observed.attempts,
                    "photon_acknowledged": observed.acknowledged,
                }
            )
        )
    finally:
        client.table("teacher_reviews").delete().eq("session_id", session_id).execute()
        client.table("seat_state").delete().eq("seat_id", seat_id).execute()


if __name__ == "__main__":
    main()
