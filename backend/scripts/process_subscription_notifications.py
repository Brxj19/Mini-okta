"""Send subscription reminders and expiry notices for paid plans."""

import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import async_session_factory
from app.models.organization import Organization
from app.services.billing_service import process_subscription_lifecycle_notifications


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Organization.id).where(Organization.deleted_at.is_(None))
        )
        org_ids = [row[0] for row in result.all()]

    renewal_sent = 0
    cancel_sent = 0
    expired = 0
    failed = 0

    for org_id in org_ids:
        async with async_session_factory() as db:
            try:
                org = await db.get(Organization, org_id)
                if not org:
                    continue
                outcome = await process_subscription_lifecycle_notifications(db, org)
                renewal_sent += int(outcome["renewal_reminder"])
                cancel_sent += int(outcome["cancel_reminder"])
                expired += int(outcome["expired"])
                await db.commit()
            except Exception as exc:
                failed += 1
                await db.rollback()
                print(f"Failed to process subscription notifications for {org_id}: {exc}")

    print(
        "Subscription notification processing complete. "
        f"renewal_sent={renewal_sent} cancel_sent={cancel_sent} expired={expired} failed={failed}"
    )


if __name__ == "__main__":
    asyncio.run(main())
