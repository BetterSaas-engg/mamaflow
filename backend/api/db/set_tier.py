"""Grant a user a plan by hand.

Writes a **tier override** — a deliberate grant that outranks the subscription
projection (D47). Two uses:

  * **Testing before the app is on the stores.** A Firebase App Distribution
    build cannot make Google Play test purchases at all (that needs an internal
    testing track), so an override is the only way to exercise Pro/Family on
    Android during the tester phase. Use `--forever`.
  * **Support.** Comping a customer, or locking out a serial refunder. Use the
    default expiry — an override left on a real customer means their genuine
    cancellation never takes effect.

It deliberately does NOT write `users.tier`. That column is a projection of the
`subscriptions` table, so anything written there is reverted by the next store
event — silently, and for the person least able to diagnose it.

    python -m api.db.set_tier parent@example.com family --forever --reason "beta tester"
    python -m api.db.set_tier parent@example.com pro --days 90 --reason "support comp"
    python -m api.db.set_tier parent@example.com --clear
    python -m api.db.set_tier --list

Refuses an unknown tier rather than writing a value that would degrade to free
at read time, which looks exactly like the grant silently not working.
"""

import argparse
import asyncio
import datetime

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.user import User
from api.services.entitlements import TIERS, entitlements_for
from api.services.households import plan_tier
from api.services.mail_connections import plan_connection_count
from api.services.subscriptions import clear_override, effective_tier
from api.services.users import normalize_email

DEFAULT_DAYS = 30


async def _find(db, email: str) -> User:
    rows = await db.execute(
        select(User).where(
            User.email == normalize_email(email), User.deleted_at.is_(None)
        )
    )
    user = rows.scalar_one_or_none()
    if user is None:
        print(f"No active user with email {email}")
        raise SystemExit(1)
    return user


async def set_tier(email: str, tier: str, days: int | None, reason: str) -> None:
    async with AsyncSessionLocal() as db:
        user = await _find(db, email)
        before = effective_tier(user)
        ent = entitlements_for(tier)

        # Warn when the grant is smaller than what the account already uses.
        # Nothing is taken away — members keep sharing and mailboxes keep
        # syncing until someone leaves or disconnects — but silence here would
        # hide exactly the case that strands a household.
        member_rows = await db.execute(
            select(User.id).where(
                User.household_id == user.household_id,
                User.household_id.is_not(None),
                User.deleted_at.is_(None),
            )
        )
        member_count = len(list(member_rows))
        if member_count > ent.members:
            print(
                f"WARNING: household of {member_count}, but {tier} allows "
                f"{ent.members}. Existing members keep sharing until one leaves."
            )
        mailboxes = await plan_connection_count(db, user)
        if mailboxes > ent.mailboxes:
            print(
                f"WARNING: plan uses {mailboxes} mailboxes, but {tier} allows "
                f"{ent.mailboxes}. Existing ones keep syncing until one is "
                "disconnected."
            )

        user.tier_override = tier
        user.tier_override_reason = reason
        user.tier_override_expires_at = (
            None
            if days is None
            else datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=days)
        )
        await db.commit()

        expiry = "never expires" if days is None else f"expires in {days}d"
        print(
            f"{email}: {before} -> {tier} ({expiry}) "
            f"[{ent.mailboxes} mailbox(es), {ent.members} member(s), "
            f"ads {'on' if ent.ads else 'off'}]"
        )
        if days is None:
            print(
                "  note: no expiry. Right for a tester, wrong for a real "
                "customer — their cancellation would never take effect."
            )


async def clear(email: str) -> None:
    async with AsyncSessionLocal() as db:
        user = await _find(db, email)
        before = effective_tier(user)
        clear_override(user)
        await db.commit()
        print(f"{email}: override cleared ({before} -> {user.tier}, from billing)")


async def list_users() -> None:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
        )
        users = list(rows.scalars())
        if not users:
            print("no active users")
            return
        print(f"{'EFFECTIVE':<10} {'BILLING':<8} {'OVERRIDE':<28} EMAIL")
        for user in users:
            # Effective beside the projection is what makes "why is this person
            # on Pro?" answerable at a glance.
            effective = await plan_tier(db, user)
            if user.tier_override:
                expiry = user.tier_override_expires_at
                when = "forever" if expiry is None else expiry.date().isoformat()
                note = f"{user.tier_override} ({when}) {user.tier_override_reason or ''}"
            else:
                note = "-"
            print(f"{effective:<10} {user.tier:<8} {note[:28]:<28} {user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="set_tier",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("email", nargs="?")
    parser.add_argument("tier", nargs="?", choices=list(TIERS))
    parser.add_argument("--list", action="store_true", help="show every user's plan")
    parser.add_argument("--clear", action="store_true", help="remove the override")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"expiry in days (default {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--forever", action="store_true", help="no expiry — for pre-launch testers"
    )
    parser.add_argument("--reason", default="", help="why (shown in --list)")
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_users())
        return
    if args.clear:
        if not args.email:
            parser.error("--clear needs an email")
        asyncio.run(clear(args.email))
        return
    if not args.email or not args.tier:
        parser.error("need an email and a tier (or --list / --clear)")
    if not args.reason:
        # An override with no reason becomes an unexplained grant nobody dares
        # remove later.
        parser.error("--reason is required, so --list stays meaningful")
    asyncio.run(
        set_tier(
            args.email, args.tier, None if args.forever else args.days, args.reason
        )
    )


if __name__ == "__main__":
    main()
