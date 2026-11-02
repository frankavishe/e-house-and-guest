"""notify() and the sms.send handler (T024)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import catalog
from app.integrations import get_sms_provider, override_sms
from app.integrations.sms.base import SmsResult
from app.integrations.sms.console import ConsoleSmsProvider
from app.jobs.models import Job
from app.notifications.handlers import send_sms
from app.notifications.models import Channel, Notification, NotificationStatus
from app.notifications.service import notify
from tests.factories import make_user


@pytest.fixture
def test_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """A throwaway template in both catalogs, so tests don't depend on story templates."""
    for loc, text in (("sw", "Habari {name}"), ("en", "Hello {name}")):
        monkeypatch.setitem(catalog(loc), "notifications.test.ping.sms", text)


async def test_notify_creates_rows_and_queues_sms(db: AsyncSession, test_template) -> None:
    user = await make_user(db, language="en")
    created = await notify(db, user.id, "test.ping", {"name": "Asha"})

    assert {n.channel for n in created} == {Channel.SMS, Channel.IN_APP}
    sms = next(n for n in created if n.channel == Channel.SMS)
    in_app = next(n for n in created if n.channel == Channel.IN_APP)
    assert sms.status == NotificationStatus.QUEUED and in_app.status == NotificationStatus.SENT
    job = (await db.execute(select(Job).where(Job.kind == "sms.send"))).scalar_one()
    assert job.payload == {"notification_id": str(sms.id)}


async def test_sms_handler_sends_in_user_language_once(db: AsyncSession, test_template) -> None:
    sms_provider = get_sms_provider()
    assert isinstance(sms_provider, ConsoleSmsProvider)
    user = await make_user(db, language="sw")
    [sms] = await notify(db, user.id, "test.ping", {"name": "Juma"}, channels=[Channel.SMS])

    await send_sms(db, {"notification_id": str(sms.id)})
    await send_sms(db, {"notification_id": str(sms.id)})  # re-run is a no-op

    sent = [m for m in sms_provider.outbox if m.to == user.phone]
    assert [m.text for m in sent] == ["Habari Juma"]
    row = await db.get(Notification, sms.id)
    assert row is not None and row.status == NotificationStatus.SENT and row.provider_ref


async def test_sms_failure_raises_for_retry(db: AsyncSession, test_template) -> None:
    class Failing:
        name = "failing"

        async def send(self, *, to: str, text: str) -> SmsResult:
            return SmsResult(ok=False, failure_reason="network")

    user = await make_user(db)
    [sms] = await notify(db, user.id, "test.ping", {"name": "x"}, channels=[Channel.SMS])
    original = get_sms_provider()
    override_sms(Failing())
    try:
        with pytest.raises(RuntimeError):
            await send_sms(db, {"notification_id": str(sms.id)})
    finally:
        override_sms(original)
    row = await db.get(Notification, sms.id)
    assert row is not None and row.status == NotificationStatus.QUEUED
