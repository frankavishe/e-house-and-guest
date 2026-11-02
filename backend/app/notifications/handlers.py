"""Worker handler that delivers queued SMS notifications (idempotent)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User, UserStatus
from app.core import clock
from app.integrations import get_sms_provider
from app.jobs.registry import handler
from app.notifications.models import Notification, NotificationStatus
from app.notifications.service import SMS_JOB, render


@handler(SMS_JOB)
async def send_sms(session: AsyncSession, payload: dict[str, Any]) -> None:
    notification = await session.get(
        Notification, uuid.UUID(payload["notification_id"]), with_for_update=True
    )
    if notification is None or notification.status != NotificationStatus.QUEUED:
        return  # already handled (job re-run after a crash)
    user = await session.get(User, notification.user_id)
    if user is None or user.status == UserStatus.DELETED:
        notification.status = NotificationStatus.FAILED
        return
    text = render(
        notification.event, notification.channel, notification.locale, notification.payload
    )
    result = await get_sms_provider().send(to=user.phone, text=text)
    if not result.ok:
        # Raise so the job retries with backoff; the notification stays queued.
        raise RuntimeError(f"sms failed: {result.failure_reason}")
    notification.status = NotificationStatus.SENT
    notification.sent_at = clock.now()
    notification.provider_ref = result.provider_ref
