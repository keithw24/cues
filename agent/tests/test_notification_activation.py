import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.notification_activation import send_to_teacher


def setup(monkeypatch, outcome="accepted", updated=True, **state):
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"phone_number": "+12025550101"}]),
        SimpleNamespace(
            data=[
                {
                    "notification_opt_in": True,
                    "notification_phone": "+12025550101",
                    "photon_project_id": "project",
                    "registration_attempt": "attempt",
                    **state,
                }
            ]
        ),
    ]
    client.rpc.return_value.execute.return_value.data = updated
    send = MagicMock(
        return_value=SimpleNamespace(
            returncode=0 if outcome == "accepted" else 1,
            stdout=json.dumps({"accepted": outcome == "accepted", "category": outcome}),
        )
    )
    monkeypatch.setattr("agent.notification_activation.subprocess.run", send)
    return client, send


CONFIG = {
    "SPECTRUM_PROJECT_ID": "project",
    "SPECTRUM_PROJECT_SECRET": "secret",
    "SPECTRUM_TEACHER_PHONE": "+12025550999",
}


@pytest.mark.parametrize(
    "outcome,status", [("accepted", "registered"), ("target_not_allowed", "pending")]
)
def test_pending_can_send_and_records_exact_snapshot(monkeypatch, tmp_path, outcome, status):
    client, send = setup(monkeypatch, outcome, photon_registration_status="registering")
    assert send_to_teacher(client, CONFIG, tmp_path, "owner", "Test") == status
    args = client.rpc.call_args.args
    assert args == (
        "record_teacher_notification_send",
        {
            "p_user_id": "owner",
            "p_phone": "+12025550101",
            "p_attempt": "attempt",
            "p_project_id": "project",
            "p_result": outcome,
        },
    )
    assert "SPECTRUM_TEACHER_PHONE" not in send.call_args.kwargs["env"]


@pytest.mark.parametrize(
    "state",
    [
        {"notification_opt_in": False},
        {"notification_phone": "+12025550102"},
        {"photon_project_id": "other"},
        {"registration_attempt": None},
    ],
)
def test_invalid_consent_never_sends(monkeypatch, tmp_path, state):
    client, send = setup(monkeypatch, **state)
    with pytest.raises(RuntimeError):
        send_to_teacher(client, CONFIG, tmp_path, "owner", "Test")
    send.assert_not_called()
    client.rpc.assert_not_called()


def test_stale_result_not_claimed_enabled(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, updated=False)
    with pytest.raises(RuntimeError, match="consent changed"):
        send_to_teacher(client, CONFIG, tmp_path, "owner", "Test")


def test_provider_failure_only_safe_category(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, "provider_failure")
    with pytest.raises(RuntimeError, match="provider_failure"):
        send_to_teacher(client, CONFIG, tmp_path, "owner", "Test")
    assert client.rpc.call_args.args[1]["p_result"] == "provider_failure"


def test_later_retry_after_website_activation(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, "target_not_allowed")
    assert send_to_teacher(client, CONFIG, tmp_path, "owner", "Test") == "pending"
    client, _ = setup(monkeypatch, "accepted")
    assert send_to_teacher(client, CONFIG, tmp_path, "owner", "Test") == "registered"
