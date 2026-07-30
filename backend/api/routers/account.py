import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.auth.imap_auth import ImapAuthRequest, verify_and_store_imap_mailbox
from api.auth.oauth import exchange_code_pkce
from api.auth.token_store import store_token
from api.db.session import get_db
from api.models.user import User
from api.services.account import delete_account
from api.services.entitlements import entitlements_for
from api.services.users import normalize_email
from api.services.mail_connections import (
    MailboxAlreadyConnected,
    MailboxLimitReached,
    ensure_connection,
    get_connection,
    list_connections,
    mailbox_usage,
    remove_connection,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/account", tags=["account"])


class Mailbox(BaseModel):
    id: str
    provider: str
    email: str


class MailboxUsage(BaseModel):
    connected: int
    limit: int
    can_add_another: bool


class AccountMe(BaseModel):
    """What the app needs to render the account screen and gate paid features.

    Deliberately derived server-side: the client must never compute its own
    entitlements from a tier string, or the limits end up defined in two places
    and drift the moment pricing changes.
    """

    id: str
    email: str
    provider: str
    tier: str
    ads_enabled: bool
    member_limit: int
    mailboxes: MailboxUsage


@router.get("/me", response_model=AccountMe)
async def read_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountMe:
    """The authed user's plan, limits and mailbox usage.

    Counts come from live connection rows, so the number the client shows and
    the number the cap is enforced against are the same one.
    """
    ent = entitlements_for(user.tier)
    connected, limit, can_add = await mailbox_usage(db, user)
    return AccountMe(
        id=str(user.id),
        email=user.email,
        provider=user.provider,
        # Report the RESOLVED tier, not the raw column: an unrecognised value
        # degrades to free, and the client must be told what it actually got.
        tier=ent.tier,
        ads_enabled=ent.ads,
        member_limit=ent.members,
        mailboxes=MailboxUsage(
            connected=connected, limit=limit, can_add_another=can_add
        ),
    )


@router.get("/mailboxes", response_model=list[Mailbox])
async def list_my_mailboxes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Mailbox]:
    """The mailboxes this user has connected."""
    rows = await list_connections(db, user.id)
    return [
        Mailbox(id=str(r.id), provider=r.provider, email=r.email)
        for r in rows
    ]


@router.post("/mailboxes", response_model=Mailbox, status_code=status.HTTP_201_CREATED)
async def add_mailbox(
    payload: ImapAuthRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Mailbox:
    """Connect an ADDITIONAL mailbox to the signed-in account (D44).

    Distinct from `POST /auth/imap`, which is sign-in: that establishes an
    identity, this attaches another mailbox to one that already exists. It has
    to be authenticated, or "add a mailbox" would be indistinguishable from
    "create a second account".

    The cap is checked BEFORE the credential is verified or stored — there is
    no reason to make a user wait on an IMAP round trip, or to hold a secret we
    are about to reject. ensure_connection re-checks it as the authority.
    """
    email = normalize_email(payload.email)
    connected, limit, can_add = await mailbox_usage(db, user)
    already_connected = any(
        c.email == email for c in await list_connections(db, user.id)
    )
    # Re-authenticating a mailbox that's already connected (rotated app
    # password) must never be refused for being "over" the cap.
    if not already_connected and not can_add:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {limit} mailbox"
                f"{'es' if limit != 1 else ''}. "
                "Upgrade or disconnect one to add another."
            ),
        )

    provider, verified_email = await verify_and_store_imap_mailbox(payload, request)
    try:
        connection = await ensure_connection(db, user, provider.key, verified_email)
    except MailboxAlreadyConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That mailbox is already connected to another Mamaflow "
                "account. Disconnect it there first."
            ),
        )
    except MailboxLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {exc.limit} mailbox"
                f"{'es' if exc.limit != 1 else ''}."
            ),
        )
    return Mailbox(
        id=str(connection.id),
        provider=connection.provider,
        email=connection.email,
    )


class GoogleMailboxRequest(BaseModel):
    code: str
    code_verifier: str


@router.post(
    "/mailboxes/google", response_model=Mailbox, status_code=status.HTTP_201_CREATED
)
async def add_google_mailbox(
    payload: GoogleMailboxRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Mailbox:
    """Attach a second Gmail account to the signed-in user (D44/D45).

    Sign-in ties identity to the mailbox; this does not — the address comes
    from Google's **verified id_token**, never from the caller, so a user
    cannot claim a mailbox they don't control.

    Order matters: the connection is recorded BEFORE the credential is stored.
    Storing first meant a connect we then rejected had already overwritten the
    credential — including another account's, since the store is keyed by
    (email, provider) with no user in the key (the 2026-07-30 audit BLOCK).
    The reverse failure is benign: a row with no credential just reports
    "reauth needed" and the user retries.
    """
    try:
        creds_data, google_email = await exchange_code_pkce(
            payload.code, payload.code_verifier
        )
    except Exception as exc:
        # Types-only: Google's error code is safe, the raw body is not.
        _log.warning("add-mailbox exchange failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authorization code",
        )

    email = normalize_email(google_email)
    try:
        connection = await ensure_connection(db, user, "google", email)
    except MailboxAlreadyConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That mailbox is already connected to another Mamaflow "
                "account. Disconnect it there first."
            ),
        )
    except MailboxLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {exc.limit} mailbox"
                f"{'es' if exc.limit != 1 else ''}. "
                "Upgrade or disconnect one to add another."
            ),
        )

    # Blocking gRPC on the secret-manager backend — off the loop (D4).
    await asyncio.to_thread(store_token, email, creds_data, "google")
    return Mailbox(
        id=str(connection.id),
        provider=connection.provider,
        email=connection.email,
    )


@router.delete("/mailboxes/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_mailbox(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect a mailbox: stop syncing it and destroy its credential.

    Scoped to the authed user — a connection id alone must never be enough to
    disconnect someone else's mailbox. An unknown id 404s rather than silently
    succeeding, so the client can tell "already gone" from "not yours".
    """
    connection = await get_connection(db, user.id, connection_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found"
        )
    await remove_connection(db, user, connection)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete the authed user's account + data and revoke Gmail access."""
    await delete_account(db, user)
