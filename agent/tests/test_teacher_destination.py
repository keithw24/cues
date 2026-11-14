import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.notifications import spectrum_notifier
from agent.teacher_review import TeacherReviewStore
from agent.tests.test_teacher_review import assessment, request


@pytest.mark.parametrize(
    "owner,phone", [("teacher-a", "+12025550101"), ("teacher-b", "+12025550102")]
)
def test_dynamic_uses_only_review_session_owner(monkeypatch, tmp_path, owner, phone):
    client = MagicMock()
    session_query = client.table.return_value.select.return_value.eq.return_value
    session_query.execute.side_effect = [
        SimpleNamespace(data=[{"teacher_id": owner}]),
        SimpleNamespace(data=[{"phone_number": phone}]),
    ]
    send = MagicMock(return_value=SimpleNamespace(returncode=0, stdout='{"accepted":true}'))
    monkeypatch.setattr("agent.notifications.subprocess.run", send)
    review = TeacherReviewStore().request_teacher_review(request(), assessment())
    notifier = spectrum_notifier(
        {
            "SPECTRUM_PROJECT_ID": "project",
            "SPECTRUM_PROJECT_SECRET": "secret",
            "SPECTRUM_TEACHER_PHONE": "+12025550999",
            "CUES_USE_STATIC_TEACHER_PHONE": "0",
        },
        tmp_path,
        client,
    )
    notifier.notify_pending_review(review)
    assert json.loads(send.call_args.kwargs["input"])["destination"] == phone
    assert "SPECTRUM_TEACHER_PHONE" not in send.call_args.kwargs["env"]
    assert "+12025550999" not in send.call_args.kwargs["input"]
    client.table.return_value.select.return_value.eq.assert_any_call("user_id", owner)
    assert phone not in review.model_dump_json()


@pytest.mark.parametrize("missing", ["owner", "profile", "phone"])
def test_dynamic_missing_destination_never_falls_back(monkeypatch, tmp_path, missing):
    client = MagicMock()
    responses = [SimpleNamespace(data=[] if missing == "owner" else [{"teacher_id": "a"}])]
    responses.append(SimpleNamespace(data=[] if missing == "profile" else [{"phone_number": None}]))
    client.table.return_value.select.return_value.eq.return_value.execute.side_effect = responses
    send = MagicMock()
    monkeypatch.setattr("agent.notifications.subprocess.run", send)
    store = TeacherReviewStore()
    review = store.request_teacher_review(request(), assessment())
    notifier = spectrum_notifier(
        {
            "SPECTRUM_PROJECT_ID": "project",
            "SPECTRUM_PROJECT_SECRET": "secret",
            "SPECTRUM_TEACHER_PHONE": "+12025550999",
        },
        tmp_path,
        client,
    )
    with pytest.raises(RuntimeError):
        notifier.notify_pending_review(review)
    send.assert_not_called()
    assert store.get_review(review.id).status == "pending"
