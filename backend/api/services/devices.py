"""Device registration for push notifications."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.base import _utcnow
from api.models.device import Device
from api.models.user import User


async def register_device(
    db: AsyncSession,
    user: User,
    fcm_token: str,
    platform: str,
) -> Device:
    """Upsert a device by fcm_token: a token uniquely identifies a device, so
    re-registration (token refresh / account switch) updates the existing row
    rather than creating a duplicate. Reactivates a soft-deleted token.

    Security trade-off (tracked for the FCM-sender phase): "last registration
    wins" reassigns the row's user_id, which is REQUIRED for the legitimate
    device-switch case (same physical device, user A logs out → user B logs in,
    B's app holds the same FCM token and must claim it). At the backend layer
    possession of the FCM token is the device-identity proof, so switch and
    hijack are indistinguishable here. Residual risk: someone who obtains
    another user's opaque token could reassign it, misrouting (their own)
    pushes to that device — a low-impact integrity/DoS issue, and inert until
    the push sender exists. Revisit when building the sender (e.g. require an
    app-side unregister, or token attestation).
    """
    existing = (
        await db.execute(select(Device).where(Device.fcm_token == fcm_token))
    ).scalar_one_or_none()

    if existing is not None:
        existing.user_id = user.id
        existing.platform = platform
        existing.deleted_at = None
        device = existing
    else:
        device = Device(user_id=user.id, fcm_token=fcm_token, platform=platform)
        db.add(device)

    await db.commit()
    await db.refresh(device)
    return device


async def unregister_device(db: AsyncSession, user: User, fcm_token: str) -> None:
    """Soft-delete the caller's registration for this token (sign-out path).

    Scoped to the authed user: if the token has since been re-registered to a
    different account (shared-device switch), a stale instance's unregister is
    a no-op. Idempotent — an unknown or already-deleted token is not an error.
    """
    device = (
        await db.execute(
            select(Device).where(
                Device.fcm_token == fcm_token,
                Device.user_id == user.id,
                Device.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if device is not None:
        device.deleted_at = _utcnow()
        await db.commit()
