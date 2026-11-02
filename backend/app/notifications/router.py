"""In-app notification feed (FR-019, contracts/rest-api.md "Messaging & reviews")."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.core import clock
from app.core.deps import CurrentUser, Session
from app.notifications.models import Channel, Notification
from app.notifications.service import render

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    event: str
    text: str
    booking_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    page: int
    page_size: int
    total: int
    unread_count: int


class MarkRead(BaseModel):
    """`ids` to mark read; omitted means all of the user's notifications."""

    ids: Annotated[list[uuid.UUID], Field(max_length=200)] | None = None


class UnreadCount(BaseModel):
    unread_count: int


def _feed(user_id: uuid.UUID):  # type: ignore[no-untyped-def]
    return (Notification.user_id == user_id, Notification.channel == Channel.IN_APP)


async def _unread(session: Session, user_id: uuid.UUID) -> int:
    count = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(*_feed(user_id), Notification.read_at.is_(None))
    )
    return count.scalar_one()


def _booking_id(payload: dict[str, object]) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(payload["booking_id"]))
    except (KeyError, ValueError):
        return None


@router.get("/notifications", response_model=NotificationPage)
async def list_notifications(
    user: CurrentUser,
    session: Session,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> NotificationPage:
    """Newest first, rendered in the user's language."""
    total = (
        await session.execute(select(func.count()).select_from(Notification).where(*_feed(user.id)))
    ).scalar_one()
    rows = await session.execute(
        select(Notification)
        .where(*_feed(user.id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return NotificationPage(
        items=[
            NotificationOut(
                id=n.id,
                event=n.event,
                text=render(n.event, Channel.IN_APP, user.language, n.payload),
                booking_id=_booking_id(n.payload),
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n in rows.scalars()
        ],
        page=page,
        page_size=page_size,
        total=total,
        unread_count=await _unread(session, user.id),
    )


@router.post("/notifications/read", response_model=UnreadCount)
async def mark_read(body: MarkRead, user: CurrentUser, session: Session) -> UnreadCount:
    stmt = (
        update(Notification)
        .where(*_feed(user.id), Notification.read_at.is_(None))
        .values(read_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    if body.ids is not None:
        stmt = stmt.where(Notification.id.in_(body.ids))
    await session.execute(stmt)
    await session.commit()
    return UnreadCount(unread_count=await _unread(session, user.id))
