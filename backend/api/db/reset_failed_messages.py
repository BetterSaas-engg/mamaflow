"""Re-open messages we gave up extracting, so the next sync retries them.

Why this exists (2026-07-27 security audit, D39): bounded retries mark a
message "permanent" after a 400/422 on the assumption the fault is in THAT
message. A *systemic* fault — the 2026-07-15 invalid-tool-schema incident
400'd every extraction — would instead mass-blacklist every message hit
during the bad window, and once the root cause is fixed nothing would ever
re-open them. That is silent data loss (events never extracted), not a cost
issue, so it needs a recovery path rather than a DB hand-edit.

Only clears FAILURE state — successes (failure_kind IS NULL) are untouched,
so nothing is ever re-sent to Claude that already worked. Idempotent.

Usage:
    python -m api.db.reset_failed_messages                    # all users
    python -m api.db.reset_failed_messages --kind permanent   # only give-ups
    python -m api.db.reset_failed_messages --email a@b.com    # one user
"""

import argparse
import asyncio
import datetime
import logging

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.synced_message import SyncedMessage
from api.models.user import User

_log = logging.getLogger(__name__)


async def reset_failed_messages(kind: str | None = None, email: str | None = None) -> int:
    """Delete failure markers so the messages become eligible again.

    A failure marker exists only to suppress retries; removing it restores the
    pre-failure state exactly. Rows that recorded a SUCCESS are never touched.
    Returns the number of markers cleared.
    """
    async with AsyncSessionLocal() as db:
        stmt = select(SyncedMessage).where(
            SyncedMessage.failure_kind.is_not(None),
            SyncedMessage.deleted_at.is_(None),
        )
        if kind:
            stmt = stmt.where(SyncedMessage.failure_kind == kind)
        if email:
            user = (
                await db.execute(select(User).where(User.email == email.strip().lower()))
            ).scalar_one_or_none()
            if user is None:
                _log.warning("reset: no user for that email; nothing to do")
                return 0
            stmt = stmt.where(SyncedMessage.user_id == user.id)

        rows = (await db.execute(stmt)).scalars().all()
        for row in rows:
            # Soft-delete the marker (never hard-delete — project convention);
            # existing_message_ids filters deleted_at IS NULL, so the message
            # becomes eligible for the next sync.
            row.deleted_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()
        # Counts only, never content (audit rule).
        _log.info("reset: cleared %d failure marker(s)", len(rows))
        return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["permanent", "transient"], default=None)
    parser.add_argument("--email", default=None)
    args = parser.parse_args()
    count = asyncio.run(reset_failed_messages(kind=args.kind, email=args.email))
    print(f"cleared {count} failure marker(s); the next sync will retry them")


if __name__ == "__main__":
    main()
