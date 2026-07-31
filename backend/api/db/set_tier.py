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
        user.tier = tier
        await db.commit()
        ent = entitlements_for(tier)
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
