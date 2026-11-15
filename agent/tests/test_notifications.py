from types import SimpleNamespace

import pytest

from agent.notifications import spectrum_notifier
from agent.tests.test_supabase_teacher_review import database  # noqa: F401, F811


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
            "SPECTRUM_TEACHER_PHONE": "+12025550101",
            "CUES_USE_STATIC_TEACHER_PHONE": "1",
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


def _static_review_send(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout='{"accepted":true}')

    monkeypatch.setattr("agent.notifications.subprocess.run", run)
    for name in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET", "SPECTRUM_TEACHER_PHONE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CUES_USE_STATIC_TEACHER_PHONE", raising=False)
    return calls


def test_credentials_saved_after_worker_start_are_used_without_restart(monkeypatch, tmp_path):
    from agent.teacher_review import TeacherReviewStore
    from agent.tests.test_teacher_review import assessment, request

    calls = _static_review_send(monkeypatch)
    # The worker starts before cues/.env holds the Photon project.
    notifier = spectrum_notifier({}, tmp_path)
    review = TeacherReviewStore().request_teacher_review(request(), assessment())
    with pytest.raises(RuntimeError, match="cues/.env"):
        notifier.notify_pending_review(review)
    assert calls == []

    (tmp_path / "cues").mkdir()
    (tmp_path / "cues/.env").write_text(
        "SPECTRUM_PROJECT_ID=project\nSPECTRUM_PROJECT_SECRET=secret\n"
        "SPECTRUM_TEACHER_PHONE=+12025550101\nCUES_USE_STATIC_TEACHER_PHONE=1\n"
    )
    notifier.notify_pending_review(review)
    assert calls[0]["env"]["SPECTRUM_PROJECT_ID"] == "project"
    assert calls[0]["env"]["SPECTRUM_PROJECT_SECRET"] == "secret"


def test_missing_credentials_log_the_reason_and_keep_the_review(
    database,  # noqa: F811
    monkeypatch,
    tmp_path,
    caplog,
):
    from agent.supabase_teacher_review import SupabaseTeacherReviewStore
    from agent.tests.test_supabase_teacher_review import assessment, evaluation

    calls = _static_review_send(monkeypatch)
    _, client = database
    store = SupabaseTeacherReviewStore(client, notifier=spectrum_notifier({}, tmp_path))
    with caplog.at_level("ERROR"):
        review = store.request_teacher_review(evaluation(), assessment())
    assert store.get_review(review.id).status == "pending"
    assert calls == []
    assert "Spectrum project credentials are missing" in caplog.text
