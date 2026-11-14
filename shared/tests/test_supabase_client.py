from unittest.mock import MagicMock

import pytest

from shared import supabase_client


@pytest.fixture(autouse=True)
def clear_factory_cache(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    supabase_client.get_client.cache_clear()
    yield
    supabase_client.get_client.cache_clear()


@pytest.mark.parametrize("configured", ["none", "url_only", "key_only"])
def test_vision_optional_client_behavior_is_preserved(monkeypatch, configured):
    create = MagicMock()
    monkeypatch.setattr("supabase.create_client", create)
    if configured == "url_only":
        monkeypatch.setenv("SUPABASE_URL", "https://offline.invalid")
    if configured == "key_only":
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "offline-test-key")
    assert supabase_client.get_client() is None
    create.assert_not_called()


def test_both_components_reuse_the_shared_client_factory(monkeypatch):
    from vision.supabase_client import get_client as vision_get_client

    client = object()
    create = MagicMock(return_value=client)
    monkeypatch.setattr("supabase.create_client", create)
    assert vision_get_client is supabase_client.get_client
    assert supabase_client.get_client("https://offline.invalid", "offline-test-key") is client
    assert vision_get_client("https://offline.invalid", "offline-test-key") is client
    create.assert_called_once_with("https://offline.invalid", "offline-test-key")
