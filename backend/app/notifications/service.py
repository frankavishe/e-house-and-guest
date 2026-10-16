"""`notify()`: record a notification per channel and queue SMS delivery (FR-019, R11).

Templates live in `app/i18n/{sw,en}.json` under `notifications.<event>.<channel>` (falling
back to `.sms`) and are rendered in the recipient's language. SMS goes through the job
outbox, so a provider failure never rolls back the business change that triggered it.
"""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.core import clock
from app.core.i18n import catalog, t
from app.jobs import service as jobs
from app.notifications.models import Channel, Notification, NotificationStatus

SMS_JOB = "sms.send"


def template_key(event: str, channel: Channel) -> str:
    key = f"notifications.{event}.{channel.value}"
    return key if key in catalog("sw") else f"notifications.{event}.sms"


def render(event: str, channel: Channel, locale: str, payload: dict[str, Any]) -> str:
    return t(template_key(event, channel), locale, **payload)


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    event: str,
    payload: dict[str, Any] | None = None,
    channels: Iterable[Channel] = (Channel.SMS, Channel.IN_APP),
) -> list[Notification]:
    """Create notifications in the caller's transaction; SMS is sent by the worker."""
    user = await session.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    now = clock.now()
    created: list[Notification] = []
    for channel in channels:
        is_sms = channel == Channel.SMS
        n = Notification(
            user_id=user.id,
            event=event,
            channel=channel,
            locale=user.language,
            payload=payload or {},
            status=NotificationStatus.QUEUED if is_sms else NotificationStatus.SENT,
            sent_at=None if is_sms else now,
        )
        session.add(n)
        await session.flush()
        if is_sms:
            await jobs.enqueue(
                session, SMS_JOB, {"notification_id": str(n.id)}, dedupe_key=f"sms:{n.id}"
            )
        created.append(n)
    return created
