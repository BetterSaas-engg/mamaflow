from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.user import User
from api.services.account import delete_account
from api.services.entitlements import entitlements_for
from api.services.mailboxes import mailbox_usage

router = APIRouter(prefix="/api/v1/account", tags=["account"])


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
async def read_me(user: User = Depends(get_current_user)) -> AccountMe:
    """The authed user's plan, limits and mailbox usage.

    Counts are computed, never stored: `connected` reads the credential store,
    so a revoked app password frees the slot immediately instead of leaving the
    user stuck at their own cap.
    """
    ent = entitlements_for(user.tier)
    connected, limit, can_add = await mailbox_usage(user)
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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete the authed user's account + data and revoke Gmail access."""
    await delete_account(db, user)
