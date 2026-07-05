"""Re-normalize existing items' event_date to ISO YYYY-MM-DD. Idempotent.

Items extracted before the ISO-date fix (or with a bundled time) carry a prose
event_date that the agenda/calendar can't place. This re-runs the normalizer
over the stored string only — it never re-fetches or re-extracts the email.

Usage: python -m api.db.backfill_dates
"""

import asyncio
import email.utils
import logging
import re

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.item import Item
from api.services.ai_extractor import normalize_item_date

_log = logging.getLogger(__name__)
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


async def backfill_item_dates(db) -> int:
    """Rewrite non-ISO event_date values to ISO in place. Returns the count
    fixed. Uses each item's created_at as the year reference for yearless
    prose dates. Idempotent: values already ISO or still unparseable are left
    untouched."""
    result = await db.execute(
        select(Item).where(Item.event_date.is_not(None), Item.deleted_at.is_(None))
    )
    fixed = 0
    for item in result.scalars().all():
        current = item.event_date
        if _ISO.match(current):
            continue
        ref = email.utils.format_datetime(item.created_at)
        normalized = normalize_item_date(current, ref)
        if normalized and _ISO.match(normalized) and normalized != current:
            item.event_date = normalized
            fixed += 1
    await db.commit()
    _log.info("date backfill: %d item(s) normalized", fixed)
    return fixed


async def _main() -> None:
    async with AsyncSessionLocal() as db:
        n = await backfill_item_dates(db)
        print(f"backfilled {n} item date(s)")


if __name__ == "__main__":
    asyncio.run(_main())
