from types import SimpleNamespace

import pytest

from agent.notifications import spectrum_notifier


@pytest.mark.parametrize("success", [False, True])
def test_spectrum_sender_uses_backend_env_and_bounded_subprocess(monkeypatch, tmp_path, success):
    from agent.teacher_review import TeacherReviewStore
    from agent.tests.test_teacher_review import assessment, request

    calls = []

    def run(args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            returncode=0 if success else 1, stdout='{"accepted":true}' if success else ""
        )

    monkeypatch.setattr("agent.notifications.subprocess.run", run)
    notifier = spectrum_notifier(
        {
            "SPECTRUM_PROJECT_ID": "project",
            "SPECTRUM_PROJECT_SECRET": "secret",
            "SPECTRUM_TEACHER_PHONE": "test-destination",
        },
        tmp_path,
    )
    review = TeacherReviewStore().request_teacher_review(request(), assessment())
    if success:
        notifier.notify_pending_review(review)
    else:
        with pytest.raises(RuntimeError):
            notifier.notify_pending_review(review)
    assert calls[0]["timeout"] == 25
    assert calls[0]["env"]["SPECTRUM_PROJECT_SECRET"] == "secret"
    assert "secret" not in calls[0]["input"]
    assert review.assessment.rationale not in calls[0]["input"]
