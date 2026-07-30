"""IMAP app-password sign-in (Yahoo/Rogers, iCloud) — the connection IS the
sign-in (PM decision, D38): provider picker → email + app password → a real
IMAP login proves mailbox ownership → same app JWT as Google users → the
credential is stored server-side (D4: token store, never the DB) for the
hourly background sync.

Kept separate from oauth.py so that module stays Google-only.

Security posture:
  - app_password is a pydantic SecretStr — validation errors / reprs can
    never echo it; it is read exactly once, into the credential dict.
  - types-only logging: imaplib error text can embed server responses, so
    only exception class names are ever logged.
  - brute-force throttle (auth_throttle) — per-IP and per-email windows;
    provider outages (503) are not counted against the caller.
"""

import asyncio
import datetime
import imaplib
import logging
import re
import socket
import ssl

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import create_access_token
from api.auth.oauth import MobileAuthResponse, MobileAuthUser
from api.auth.token_store import store_token
from api.config.settings import settings
from api.db.session import get_db
from api.services import auth_throttle
from api.services.mail_providers import get_provider
from api.services.mail_connections import ensure_connection
from api.services.users import get_or_create_user, normalize_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_log = logging.getLogger(__name__)


# Rejects control chars — CR/LF here is an IMAP command-injection vector:
# imaplib.login() sends the username UNQUOTED and does not escape CR/LF in the
# quoted password, so a newline would split the LOGIN into extra IMAP commands
# on the wire to Yahoo/Apple. Validated once at the boundary; the reader only
# ever replays what was accepted here.
_EMAIL_RE = re.compile(r"^[^\s@\x00]+@[^\s@\x00]+\.[^\s@\x00]+$")
_CONTROL_RE = re.compile(r"[\r\n\x00]")


class ImapAuthRequest(BaseModel):
    provider: str
    email: str
    app_password: SecretStr

    @field_validator("provider")
    @classmethod
    def _clean_provider(cls, v: str) -> str:
        if _CONTROL_RE.search(v):
            raise ValueError("invalid provider")
        return v

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        cleaned = v.strip()
        if not _EMAIL_RE.match(cleaned):
            raise ValueError("invalid email address")
        # Return the validated (stripped) value so no outer whitespace/CRLF can
        # survive to imaplib, rather than relying on a later normalize step.
        return cleaned

    @field_validator("app_password")
    @classmethod
    def _no_control_in_password(cls, v: SecretStr) -> SecretStr:
        if _CONTROL_RE.search(v.get_secret_value()):
            raise ValueError("invalid app password")
        return v


class _MailboxUnavailable(Exception):
    """Login succeeded but INBOX select failed (e.g. iCloud Mail not enabled)."""


def _verify_imap_login(host: str, port: int, username: str, password: str) -> None:
    """Prove the credential works AND the mailbox is readable. Raises:
    imaplib.IMAP4.error (bad credential), _MailboxUnavailable (post-auth
    select failure), OSError family (provider unreachable)."""
    conn = imaplib.IMAP4_SSL(host, port, timeout=settings.imap_timeout_seconds)
    try:
        conn.login(username, password)
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise _MailboxUnavailable
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def verify_and_store_imap_mailbox(payload: "ImapAuthRequest", request: Request):
    """Throttle, validate, prove the credential against the real IMAP server,
    and store it. Returns (provider, email).

    Shared by sign-in and by adding a mailbox to an existing account (D44), so
    the two paths cannot drift on validation, throttling or error wording — the
    credential surface is the same one either way.
    """
    client_ip = request.client.host if request.client else "unknown"
    email = normalize_email(payload.email)

    allowed, retry_after = auth_throttle.check(client_ip, email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again in a few minutes.",
            headers={"Retry-After": str(retry_after)},
        )

    provider = get_provider(payload.provider)
    if provider is None or provider.auth_kind != "imap-app-password":
        raise HTTPException(status_code=400, detail="Unknown email provider.")

    # App passwords are commonly displayed with spaces ("abcd efgh …") —
    # normalize so a copy-paste with spaces still works.
    app_password = payload.app_password.get_secret_value().replace(" ", "")
    if not app_password:
        raise HTTPException(status_code=401, detail=_wrong_password_detail(provider))

    try:
        await asyncio.to_thread(
            _verify_imap_login, provider.imap_host, provider.imap_port, email, app_password
        )
    except imaplib.IMAP4.error as exc:
        auth_throttle.record_failure(client_ip, email)
        _log.warning("imap auth failed (%s/%s)", provider.key, type(exc).__name__)
        raise HTTPException(status_code=401, detail=_wrong_password_detail(provider))
    except _MailboxUnavailable:
        auth_throttle.record_failure(client_ip, email)
        _log.warning("imap auth: mailbox unavailable (%s)", provider.key)
        raise HTTPException(
            status_code=401,
            detail=(
                f"Signed in, but the mailbox isn't accessible. Check that "
                f"{provider.display_name} email is enabled for this account."
            ),
        )
    except (socket.gaierror, TimeoutError, ssl.SSLError, OSError) as exc:
        # Provider-side/network problem — NOT the caller's fault; deliberately
        # not counted as a throttle failure (an outage must not lock users out).
        _log.warning("imap auth: provider unreachable (%s/%s)", provider.key, type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail=f"Can't reach {provider.display_name} right now. Try again in a few minutes.",
        )

    auth_throttle.record_success(email)

    credential = {
        "kind": "imap_app_password",
        "provider": provider.key,
        "username": email,
        "app_password": app_password,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    # Blocking gRPC on the secret-manager backend — off the loop (D4 path,
    # same as Google tokens).
    await asyncio.to_thread(store_token, email, credential, provider.key)
    return provider, email


@router.post("/imap", response_model=MobileAuthResponse)
async def imap_auth(
    payload: ImapAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    provider, email = await verify_and_store_imap_mailbox(payload, request)

    user = await get_or_create_user(db, email, provider=provider.key)

    # Record the mailbox (D44). This no longer purges other providers: a user
    # may hold several mailboxes now, and sign-in only ever (re)connects THIS
    # one. Re-authenticating an existing mailbox is never blocked by the cap;
    # ensure_connection also destroys a superseded credential if the same
    # address comes back under a different provider, which is what keeps the
    # D38 stale-app-password guarantee once purge-on-switch is gone.
    await ensure_connection(db, user, provider.key, user.email)

    token = create_access_token(subject=str(user.id), email=user.email)
    return MobileAuthResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=MobileAuthUser(id=str(user.id), email=user.email),
    )


def _wrong_password_detail(provider) -> str:
    return (
        "Sign-in failed. Make sure you're using an app password for "
        f"{provider.display_name} — not your regular account password. "
        'Tap "How do I get one?" above for steps.'
    )
