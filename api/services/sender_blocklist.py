import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.sender_allowlist import SenderAllowlist
from api.models.sender_blocklist import SenderBlocklist
from api.schemas.blocklist import BlocklistResult


def _extract_domain(sender: str) -> str:
    """Extract domain from 'Name <user@domain.com>' or 'user@domain.com'."""
    match = re.search(r"<([^>]+)>", sender)
    email = match.group(1) if match else sender.strip()

    if "@" in email:
        return email.split("@", 1)[1].lower()
    return email.lower()


async def is_blocked_sender(sender: str, db: AsyncSession) -> BlocklistResult:
    """Check sender against allowlist then blocklist.

    Precedence: allowlist wins → blocklist blocks → unknown passes through.
    """
    domain = _extract_domain(sender)

    # 1. Allowlist — if matched, sender is explicitly allowed
    allow_result = await db.execute(
        select(SenderAllowlist)
        .where(SenderAllowlist.domain == domain)
        .where(SenderAllowlist.deleted_at.is_(None))
        .limit(1)
    )
    allow_row = allow_result.scalar_one_or_none()
    if allow_row:
        label = f" ({allow_row.label})" if allow_row.label else ""
        return BlocklistResult(
            is_blocked=False,
            reason=f"allowlisted: {domain}{label}",
            category=None,
            list_status="allowed",
        )

    # 2. Blocklist — exact domain match
    block_result = await db.execute(
        select(SenderBlocklist)
        .where(SenderBlocklist.domain == domain)
        .where(SenderBlocklist.deleted_at.is_(None))
        .limit(1)
    )
    block_row = block_result.scalar_one_or_none()
    if block_row:
        return BlocklistResult(
            is_blocked=True,
            reason=f"exact domain match: {domain}",
            category=block_row.category,
            list_status="blocked",
        )

    # 3. Blocklist — regex pattern match
    pattern_result = await db.execute(
        select(SenderBlocklist)
        .where(SenderBlocklist.pattern.is_not(None))
        .where(SenderBlocklist.deleted_at.is_(None))
    )
    for row in pattern_result.scalars():
        if re.search(row.pattern, domain, re.IGNORECASE):
            return BlocklistResult(
                is_blocked=True,
                reason=f"pattern match: {row.pattern} on {domain}",
                category=row.category,
                list_status="blocked",
            )

    # 4. Unknown — not on either list, passes through for Claude classification
    return BlocklistResult(
        is_blocked=False,
        reason="",
        category=None,
        list_status="unknown",
    )
