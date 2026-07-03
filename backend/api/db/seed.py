"""Seed default blocklist rows. Idempotent — safe to run twice.

Usage: python -m api.db.seed
"""

import asyncio

from sqlalchemy import select

from api.db.session import AsyncSessionLocal
from api.models.sender_blocklist import SenderBlocklist

FINANCIAL_DOMAINS = [
    "td.com",
    "rbc.com",
    "scotiabank.com",
    "cibc.com",
    "bmo.com",
    "paypal.com",
    "cra-arc.gc.ca",
    "irs.gov",
    "adp.com",
]

PROMOTIONAL_DOMAINS = [
    "linkedin.com",
    "etsy.com",
    "email.etsy.com",
    "wix.com",
    "team.wix.com",
    "squarespace.com",
    "mail.squarespace.com",
    "jitter.video",
    "m1.jitter.video",
    "shopify.com",
    "email.shopify.com",
    "odoo.com",
    "acquire.com",
    "news.railway.app",
    "info.vercel.com",
    "nvidia.com",
    "amazon.com",
]

# .*law\.com$ was too greedy — matched outlaw.com, inlaw.com, etc.
# Use specific firm entries instead of a broad catch-all.
PATTERNS = [
    {
        "pattern": r"(^|\.)heerlaw\.com$",
        "category": "financial",
        "reason": "Heer Law firm",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SenderBlocklist).where(SenderBlocklist.user_id.is_(None)).limit(1)
        )
        if result.scalar_one_or_none():
            print("Seed data already exists, skipping.")
            return

        rows: list[SenderBlocklist] = []

        for domain in FINANCIAL_DOMAINS:
            rows.append(SenderBlocklist(domain=domain, category="financial"))

        for domain in PROMOTIONAL_DOMAINS:
            rows.append(SenderBlocklist(domain=domain, category="promotional"))

        for p in PATTERNS:
            rows.append(
                SenderBlocklist(
                    pattern=p["pattern"],
                    category=p["category"],
                    reason=p["reason"],
                )
            )

        session.add_all(rows)
        await session.commit()
        print(f"Seeded {len(rows)} blocklist entries.")


if __name__ == "__main__":
    asyncio.run(seed())
