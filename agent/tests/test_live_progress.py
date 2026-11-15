from unittest.mock import Mock

from agent.live_progress import SupabaseProgressPublisher
from agent.tests.test_seat_state_runtime import feed, pipeline, snapshot


def test_live_progress_is_published_before_agent_and_is_revision_scoped():
    target = pipeline()
    published = []
    target.publisher = lambda observation, progress, recent: published.append(
        (observation, progress, recent)
    )
    feed(target, [snapshot(i, session_revision=0) for i in range(5)])
    assert published[-1][1].trend == "stalled"
    assert published[-1][1].stalled_seconds == 4
    assert target.agent.contexts
    feed(target, [snapshot(5, session_revision=1)])
    assert len(published[-1][2]) == 1
    assert published[-1][1].trend == "unknown"


def test_publisher_guard_parameters_and_bounded_payload():
    target = pipeline()
    feed(target, [snapshot(i, session_revision=1) for i in range(12)])
    client = Mock()
    publisher = SupabaseProgressPublisher(client)
    observation = snapshot(11, session_revision=1)
    recent = target.history.get_recent_progress_history(observation.session_id, "A", "task")
    publisher(observation, target._evaluators[(observation.session_id, "A", "task")].state, recent)
    name, args = client.rpc.call_args.args
    assert name == "publish_task_progress"
    assert args["p_revision"] == 1 and args["p_seat_id"] == "A"
    assert len(args["p_progress"]["recent"]) == 10
    assert "expression_context" not in args["p_progress"]
