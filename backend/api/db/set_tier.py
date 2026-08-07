"""Set a user's billing tier by hand.

There is no billing integration yet (D44), so tiers are assigned deliberately.
This exists so Pro/Family can actually be exercised in testing without waiting
on a payment provider — and, once billing lands, as the break-glass tool for
support.

    python -m api.db.set_tier parent@example.com family
    python -m api.db.set_tier --list

Refuses unknown tiers outright rather than writing a value that would silently
degrade to free at read time (entitlements_for), which would look like the
upgrade simply didn't work.
"""

import asyncio
import sys

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.user import User
from api.services.mail_connections import plan_connection_count
from api.services.entitlements import TIERS, entitlements_for
from api.services.users import normalize_email


async def set_tier(email: str, tier: str) -> None:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(User).where(
                User.email == normalize_email(email), User.deleted_at.is_(None)
            )
        )
        user = rows.scalar_one_or_none()
        if user is None:
            print(f"No active user with email {email}")
            raise SystemExit(1)
        before = user.tier
        # Downgrading below what the account already uses doesn't shrink
        # anything — members keep sharing and mailboxes keep syncing at the old
        # cap until someone manually leaves. Say so rather than let it pass
        # silently.
        ent = entitlements_for(tier)
        members = await db.execute(
            select(User.email).where(
                User.household_id == user.household_id,
                User.household_id.is_not(None),
                User.deleted_at.is_(None),
            )
        )
        member_count = len(list(members))
        if member_count > ent.members:
            print(
                f"WARNING: {email} is in a household of {member_count}, but "
                f"{tier} allows {ent.members}. Existing members keep sharing "
                "until one leaves."
            )
        # Plan-wide, not per-user: a Family household's mailboxes are shared
        # (D47), so counting only this user's would under-report and the
        # warning would stay silent on exactly the downgrade that strands them.
        mailbox_count = await plan_connection_count(db, user)
        if mailbox_count > ent.mailboxes:
            print(
                f"WARNING: {email} has {mailbox_count} mailboxes, but {tier} "
                f"allows {ent.mailboxes}. Existing ones keep syncing until "
                "one is disconnected."
            )
        user.tier = tier
        await db.commit()
        print(
            f"{email}: {before} -> {tier} "
            f"({ent.mailboxes} mailbox(es), {ent.members} member(s), "
            f"ads {'on' if ent.ads else 'off'})"
        )


async def list_users() -> None:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(User.email, User.tier)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at)
        )
        for email, tier in rows:
            print(f"{tier:<8} {email}")


def main() -> None:
    args = sys.argv[1:]
    if args == ["--list"]:
        asyncio.run(list_users())
        return
    if len(args) != 2:
        print(__doc__)
        raise SystemExit(2)
    email, tier = args
    if tier not in TIERS:
        print(f"Unknown tier {tier!r}. Valid: {', '.join(TIERS)}")
        raise SystemExit(2)
    asyncio.run(set_tier(email, tier))


if __name__ == "__main__":
    main()
