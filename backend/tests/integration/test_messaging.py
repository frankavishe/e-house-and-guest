"""In-app messaging between renters and owners (T125, US6, FR-028, R18)."""

import uuid
from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.models import Conversation
from app.messaging.service import mask_phones
from app.notifications.models import Channel, Notification
from tests.factories import Bookable, day_range, make_bookable, make_booking, make_user, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")

FAR = day_range(date(2026, 11, 20), date(2026, 11, 23))
PHONE_TEXT = "Nipigie 0712 345 678 au +255712345678, bei 50000"


async def _start(client: httpx.AsyncClient, b: Bookable, body: str = "Habari") -> httpx.Response:
    sign_in(client, b.renter)
    return await client.post(
        "/api/v1/conversations", json={"listing_id": str(b.listing.id), "body": body}
    )


async def _send(client: httpx.AsyncClient, conv_id: str, body: str) -> dict[str, Any]:
    r = await client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": body})
    assert r.status_code == 201, r.text
    data: dict[str, Any] = r.json()
    return data


async def _messages(
    client: httpx.AsyncClient, conv_id: str, after: int | None = None
) -> list[dict[str, Any]]:
    params = {"after": after} if after is not None else {}
    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", params=params)
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


async def _inbox(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    r = await client.get("/api/v1/conversations")
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def test_mask_phones() -> None:
    masked, changed = mask_phones(PHONE_TEXT)
    assert changed
    assert "712" not in masked and "345" not in masked
    assert "50000" in masked  # prices are not phone numbers
    assert mask_phones("Iko wazi tarehe 20?") == ("Iko wazi tarehe 20?", False)
    assert mask_phones("Namba yangu ni 255-754-111-222")[1]


async def test_renter_starts_and_reuses_conversation(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    first = await _start(client, b, "Habari, ipo wazi?")
    assert first.status_code == 201, first.text
    conv = first.json()
    assert conv["role"] == "renter"
    assert conv["listing"]["id"] == str(b.listing.id)
    assert conv["counterpart"]["name"] == b.owner.display_name

    again = await _start(client, b, "Ujumbe wa pili")
    assert again.status_code == 200, again.text
    assert again.json()["id"] == conv["id"]
    count = await db.execute(
        select(func.count()).select_from(Conversation).where(Conversation.renter_id == b.renter.id)
    )
    assert count.scalar_one() == 1
    bodies = [m["body"] for m in await _messages(client, conv["id"])]
    assert bodies == ["Habari, ipo wazi?", "Ujumbe wa pili"]


async def test_owner_cannot_start_on_own_listing(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    sign_in(client, b.owner_user)
    r = await client.post(
        "/api/v1/conversations", json={"listing_id": str(b.listing.id), "body": "hi"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "OWN_LISTING"


async def test_non_public_listing_is_404(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, status="draft")
    r = await _start(client, b)
    assert r.status_code == 404


async def test_only_participants_can_read_or_write(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    conv_id = (await _start(client, b)).json()["id"]
    outsider = await make_user(db, name="Outsider")
    sign_in(client, outsider)
    assert (await client.get(f"/api/v1/conversations/{conv_id}")).status_code == 404
    assert (await client.get(f"/api/v1/conversations/{conv_id}/messages")).status_code == 404
    r = await client.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "x"})
    assert r.status_code == 404
    assert await _inbox(client) == []

    sign_in(client, b.owner_user)
    conv = (await client.get(f"/api/v1/conversations/{conv_id}")).json()
    assert conv["role"] == "owner"
    assert conv["counterpart"]["name"] == b.renter.name
    reply = await _send(client, conv_id, "Ndiyo, ipo")
    assert reply["mine"] is True


async def test_phones_masked_until_confirmed_booking(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    conv_id = (await _start(client, b, PHONE_TEXT)).json()["id"]
    sign_in(client, b.owner_user)
    owner_reply = await _send(client, conv_id, "Yangu ni 0754 111 222")
    assert owner_reply["masked"] is True
    assert "111" not in owner_reply["body"]

    # A booking that is only requested does not reveal numbers.
    await make_booking(db, b, *FAR, status="requested")
    still = await _send(client, conv_id, "0754 111 222")
    assert still["masked"] is True

    confirmed = await make_booking(
        db, b, *day_range(date(2026, 12, 1), date(2026, 12, 3)), status="confirmed"
    )
    revealed = await _send(client, conv_id, "Yangu ni 0754 111 222")
    assert revealed["masked"] is False
    assert "0754 111 222" in revealed["body"]

    sign_in(client, b.renter)
    msgs = await _messages(client, conv_id)
    assert msgs[0]["masked"] is True and "712" not in msgs[0]["body"]  # history stays masked
    assert msgs[-1]["masked"] is False
    conv = (await client.get(f"/api/v1/conversations/{conv_id}")).json()
    assert conv["booking_id"] == str(confirmed.id)


async def test_unread_counts_and_read_marking(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    conv_id = (await _start(client, b, "Moja")).json()["id"]
    await _send(client, conv_id, "Mbili")
    assert (await _inbox(client))[0]["unread_count"] == 0  # own messages are never unread

    sign_in(client, b.owner_user)
    inbox = await _inbox(client)
    assert [(c["id"], c["unread_count"]) for c in inbox] == [(conv_id, 2)]
    assert inbox[0]["last_message"] == "Mbili"
    msgs = await _messages(client, conv_id)  # reading marks the counterpart's messages read
    assert all(not m["mine"] for m in msgs)
    assert (await _inbox(client))[0]["unread_count"] == 0

    sign_in(client, b.renter)
    mine = await _messages(client, conv_id)
    assert all(m["read_at"] is not None for m in mine)


async def test_polling_with_after(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    conv_id = (await _start(client, b, "1")).json()["id"]
    await _send(client, conv_id, "2")
    await _send(client, conv_id, "3")
    first = (await _messages(client, conv_id))[0]
    newer = await _messages(client, conv_id, after=first["seq"])
    assert [m["body"] for m in newer] == ["2", "3"]
    assert await _messages(client, conv_id, after=newer[-1]["seq"]) == []


async def test_new_message_notifies_once_while_unread(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    conv_id = (await _start(client, b, "Habari")).json()["id"]
    await _send(client, conv_id, "Uko?")

    async def owner_notes() -> list[Notification]:
        rows = await db.execute(
            select(Notification).where(
                Notification.user_id == b.owner_user.id, Notification.event == "message.received"
            )
        )
        return list(rows.scalars())

    notes = await owner_notes()
    assert len(notes) == 1
    assert notes[0].channel == Channel.IN_APP
    assert notes[0].payload["conversation_id"] == conv_id

    sign_in(client, b.owner_user)
    await _messages(client, conv_id)
    sign_in(client, b.renter)
    await _send(client, conv_id, "Tena")
    assert len(await owner_notes()) == 2


async def test_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    assert (await _start(client, b, "")).status_code == 422
    assert (await _start(client, b, "x" * 2001)).status_code == 422
    sign_in(client, b.renter)
    r = await client.post(
        "/api/v1/conversations", json={"listing_id": str(uuid.uuid4()), "body": "hi"}
    )
    assert r.status_code == 404
