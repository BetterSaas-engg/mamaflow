"""mail_reader dispatch — which reader serves which provider."""

import pytest

from api.services import mail_reader
from api.services.reader_errors import ReauthRequired


def test_google_routes_to_gmail_reader(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mail_reader.gmail_reader, "list_recent_ids",
        lambda email: calls.append(("gmail", email)) or [],
    )
    mail_reader.list_recent_ids("a@gmail.com", "google")
    assert calls == [("gmail", "a@gmail.com")]


def test_imap_providers_route_to_imap_reader(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mail_reader.imap_reader, "fetch_message_bodies",
        lambda email, ids, provider: calls.append((provider, tuple(ids))) or {},
    )
    mail_reader.fetch_message_bodies("a@rogers.com", ["m1"], "yahoo")
    mail_reader.fetch_message_bodies("b@icloud.com", ["m2"], "icloud")
    assert calls == [("yahoo", ("m1",)), ("icloud", ("m2",))]


def test_unknown_provider_raises_reauth():
    with pytest.raises(ReauthRequired):
        mail_reader.list_recent_ids("a@b.com", "aol")
    with pytest.raises(ReauthRequired):
        mail_reader.fetch_message_bodies("a@b.com", ["m"], "microsoft")  # Phase 2, not yet
