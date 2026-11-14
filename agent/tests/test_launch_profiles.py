import sys
from unittest.mock import MagicMock

import pytest

from agent import worker
from agent.escalation import DEMO_ESCALATION_CONFIG
from agent.progress import DEMO_PROGRESS_WINDOW_SECONDS


@pytest.mark.parametrize("profile", ["dev", "demo"])
def test_worker_profile_uses_existing_configuration(monkeypatch, profile):
    monkeypatch.setattr(sys, "argv", ["worker", "--profile", profile])
    for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY", "CUES_SESSION_ID"):
        monkeypatch.setenv(key, "offline-test")
    monkeypatch.setattr(worker, "ChatGroq", MagicMock())
    factory = MagicMock()
    monkeypatch.setattr(worker, "create_seat_state_runtime", factory)
    worker.main()
    kwargs = factory.call_args.kwargs
    if profile == "demo":
        assert kwargs["escalation_config"] is DEMO_ESCALATION_CONFIG
        assert kwargs["progress_window_seconds"] == DEMO_PROGRESS_WINDOW_SECONDS
    else:
        assert "escalation_config" not in kwargs
        assert "progress_window_seconds" not in kwargs
    factory.return_value.run_forever.assert_called_once()
