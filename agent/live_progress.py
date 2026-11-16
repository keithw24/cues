"""Publish evaluated summaries through the existing SeatState Realtime channel."""

from dataclasses import asdict


class SupabaseProgressPublisher:
    def __init__(self, client):
        self.client = client

    def __call__(self, snapshot, progress, recent, stalled_since=None):
        return (
            self.client.rpc(
                "publish_task_progress",
                {
                    "p_seat_id": snapshot.seat_id,
                    "p_session_id": str(snapshot.session_id),
                    "p_activity_id": snapshot.activity_id,
                    "p_revision": snapshot.session_revision,
                    "p_observed_at": snapshot.updated_at.isoformat(),
                    "p_progress": {
                        **asdict(progress),
                        "stalled_since": stalled_since.isoformat() if stalled_since else None,
                        "recent": [entry.model_dump(mode="json") for entry in recent[-10:]],
                    },
                },
            )
            .execute()
            .data
        )
