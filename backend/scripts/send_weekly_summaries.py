"""Send weekly summary emails to users who opted in."""

import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import async_session_factory
from app.models.user import User
from app.services.notification_service import send_weekly_summary_email


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(User.id).where(
                User.deleted_at.is_(None),
                User.status == "active",
            )
        )
        user_ids = [row[0] for row in result.all()]

    sent = 0
    skipped = 0
    failed = 0

    for user_id in user_ids:
        async with async_session_factory() as db:
            try:
                user = await db.get(User, user_id)
                if user and await send_weekly_summary_email(db, user):
                    sent += 1
                else:
                    skipped += 1
                await db.commit()
            except Exception as exc:
                failed += 1
                await db.rollback()
                print(f"Failed to send weekly summary for {user_id}: {exc}")

    print(f"Weekly summaries complete. sent={sent} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    asyncio.run(main())
