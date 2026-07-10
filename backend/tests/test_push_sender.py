from types import SimpleNamespace

from api.config.settings import settings
from api.services import push_sender


def test_is_configured_reflects_settings(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", "")
    assert push_sender.is_configured() is False
    monkeypatch.setattr(settings, "firebase_credentials_json", '{"x": 1}')
    assert push_sender.is_configured() is True


def test_dead_tokens_from_responses():
    class UnregisteredError(Exception):
        pass

    responses = [
        SimpleNamespace(success=True, exception=None),
        SimpleNamespace(success=False, exception=UnregisteredError()),
        SimpleNamespace(success=False, exception=ValueError("transient")),
    ]
    dead = push_sender.dead_tokens_from_responses(["a", "b", "c"], responses)
    assert dead == ["b"]  # only the permanent token error is pruned


async def test_send_digest_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", "")

    def boom(*a, **k):
        raise AssertionError("firebase must not be touched when unconfigured")

    monkeypatch.setattr(push_sender, "_send_sync", boom)
    assert await push_sender.send_digest(["tok"], "t", "b") == []


async def test_send_digest_noop_on_empty_tokens(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", '{"x": 1}')
    assert await push_sender.send_digest([], "t", "b") == []
