"""Mail provider registry — the single dispatch table for multi-provider mail.

Adding a provider is: one entry here + a reader implementing the two-function
dict contract + an auth route + a frontend tile. Validation of provider keys
happens against this registry (no DB CHECK on users.provider — D34 precedent;
the valid set grows per provider).

Rogers is NOT a separate key: rogers.com mail is Yahoo-hosted, so the frontend
shows a Rogers tile that maps to provider="yahoo" with Rogers-specific
instructions.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MailProvider:
    key: str  # "google" | "yahoo" | "icloud"   (Phase 2: "microsoft")
    display_name: str
    auth_kind: str  # "oauth-google" | "imap-app-password"  (Phase 2: "oauth-microsoft")
    imap_host: str | None  # None for API-based providers
    imap_port: int | None
    # UI hint only — never enforced (custom domains exist).
    email_domains: tuple[str, ...]
    # None => items.source_email_link stays NULL (frontend is null-safe).
    deep_link_template: str | None


PROVIDERS: dict[str, MailProvider] = {
    "google": MailProvider(
        key="google",
        display_name="Gmail",
        auth_kind="oauth-google",
        imap_host=None,
        imap_port=None,
        email_domains=("gmail.com", "googlemail.com"),
        deep_link_template="https://mail.google.com/mail/u/0/#inbox/{message_id}",
    ),
    "yahoo": MailProvider(
        key="yahoo",
        display_name="Yahoo / Rogers",
        auth_kind="imap-app-password",
        imap_host="imap.mail.yahoo.com",
        imap_port=993,
        email_domains=("yahoo.com", "yahoo.ca", "ymail.com", "rogers.com"),
        deep_link_template=None,
    ),
    "icloud": MailProvider(
        key="icloud",
        display_name="iCloud Mail",
        auth_kind="imap-app-password",
        imap_host="imap.mail.me.com",
        imap_port=993,
        email_domains=("icloud.com", "me.com", "mac.com"),
        deep_link_template=None,
    ),
}


def get_provider(key: str) -> MailProvider | None:
    return PROVIDERS.get(key)


def imap_provider_keys() -> list[str]:
    return [p.key for p in PROVIDERS.values() if p.auth_kind == "imap-app-password"]


def build_deep_link(provider_key: str, message_id: str) -> str | None:
    """Web link to the source email, or None when the provider has no stable
    per-message web URL (IMAP providers). Built server-side only — never from
    model output (audit rule)."""
    provider = PROVIDERS.get(provider_key)
    if provider is None or provider.deep_link_template is None or not message_id:
        return None
    return provider.deep_link_template.format(message_id=message_id)
