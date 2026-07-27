"""Per-user daily extraction budget — the backstop against cost runaways.

The 2026-07-27 incident (a retry loop billing ~216 calls/user/day) was
invisible until the bill arrived. Bounded retries fix that specific bug; this
caps the blast radius of the NEXT one, whatever it turns out to be. Counts
only — no content (D5 / audit rule).
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import settings
from api.models.extraction_usage import ExtractionUsageDaily

_log = logging.getLogger(__name__)


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


async def _row_for_today(db: AsyncSession, user_id) -> ExtractionUsageDaily:
    today = _today()
    result = await db.execute(
        select(ExtractionUsageDaily).where(
            ExtractionUsageDaily.user_id == user_id,
            ExtractionUsageDaily.usage_date == today,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = ExtractionUsageDaily(user_id=user_id, usage_date=today)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race on the unique (user, date) — the other transaction's row
        # is the one to use.
        await db.rollback()
        result = await db.execute(
            select(ExtractionUsageDaily).where(
                ExtractionUsageDaily.user_id == user_id,
                ExtractionUsageDaily.usage_date == today,
            )
        )
        row = result.scalar_one()
    return row


async def has_budget(db: AsyncSession, user_id) -> bool:
    """False once this user has burned today's call budget. Checked before
    each extraction so a runaway is capped mid-run, not after the fact."""
    row = await _row_for_today(db, user_id)
    return row.calls < settings.extraction_daily_call_budget


async def record_call(
    db: AsyncSession, user_id, input_tokens: int = 0, output_tokens: int = 0
) -> None:
    """Account one extraction call. Best-effort: accounting must never break
    a sync, so failures are logged (types only) and swallowed."""
    try:
        row = await _row_for_today(db, user_id)
        row.calls = (row.calls or 0) + 1
        row.input_tokens = (row.input_tokens or 0) + int(input_tokens or 0)
        row.output_tokens = (row.output_tokens or 0) + int(output_tokens or 0)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — accounting is never load-bearing
        _log.warning("extraction usage accounting failed (%s)", type(exc).__name__)
        await db.rollback()
