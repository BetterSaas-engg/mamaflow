"""Provider registry + deep-link tests."""

from api.services.mail_providers import (
    build_deep_link,
    get_provider,
    imap_provider_keys,
)


def test_google_deep_link_matches_legacy_template():
    # Regression pin: Google items must keep the exact pre-registry link shape.
    assert (
        build_deep_link("google", "abc123")
        == "https://mail.google.com/mail/u/0/#inbox/abc123"
    )


def test_imap_providers_have_no_deep_link():
    assert build_deep_link("yahoo", "msgid@host") is None
    assert build_deep_link("icloud", "msgid@host") is None


def test_unknown_provider_and_empty_id_yield_none():
    assert build_deep_link("aol", "x") is None
    assert build_deep_link("google", "") is None


def test_registry_lookups():
    assert get_provider("yahoo").imap_host == "imap.mail.yahoo.com"
    assert get_provider("icloud").imap_port == 993
    assert get_provider("nope") is None
    assert set(imap_provider_keys()) == {"yahoo", "icloud"}


def test_rogers_is_a_yahoo_domain_hint_not_a_provider():
    assert get_provider("rogers") is None
    assert "rogers.com" in get_provider("yahoo").email_domains
