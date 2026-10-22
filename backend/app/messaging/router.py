"""Messaging endpoints (contracts/rest-api.md "Messaging & reviews")."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, Session
from app.core.i18n import Locale, get_locale
from app.messaging import service
from app.messaging.schemas import (
    AfterParam,
    ConversationOut,
    ConversationStart,
    Inbox,
    MessageIn,
    MessageList,
    MessageOut,
)

router = APIRouter(tags=["messaging"])

LocaleDep = Annotated[Locale, Depends(get_locale)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Unknown conversation"}}


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": ConversationOut, "description": "Existing conversation reused"},
        404: {"description": "Unknown or non-public listing"},
        422: {"description": "`OWN_LISTING`"},
    },
)
async def start_conversation(
    body: ConversationStart,
    user: CurrentUser,
    session: Session,
    locale: LocaleDep,
    response: Response,
) -> ConversationOut:
    """Message a listing's owner. A renter has one conversation per listing; starting again
    adds the message to it (`200`)."""
    conv, created = await service.start(session, user, body.listing_id, body.body)
    out = await service.conversation_out(session, user, conv, locale)
    await session.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    return out


@router.get("/conversations", response_model=Inbox)
async def list_conversations(
    user: CurrentUser,
    session: Session,
    locale: LocaleDep,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Inbox:
    """The inbox, newest activity first, with unread counts."""
    return await service.inbox(session, user, locale, page, page_size)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut, responses=NOT_FOUND)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: Session, locale: LocaleDep
) -> ConversationOut:
    conv, _ = await service.get_for_participant(session, user, conversation_id)
    return await service.conversation_out(session, user, conv, locale)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=MessageList, responses=NOT_FOUND
)
async def list_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[AfterParam | None, Query()] = None,
) -> MessageList:
    """Oldest first. Poll with `after=<last seq>` every 10 s while the thread is open.
    Marks the counterpart's messages read."""
    items = await service.messages(session, user, conversation_id, after)
    await session.commit()
    return MessageList(items=items)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
async def send_message(
    conversation_id: uuid.UUID, body: MessageIn, user: CurrentUser, session: Session
) -> MessageOut:
    """Phone numbers are masked until the renter has a confirmed booking of the listing."""
    message = await service.send(session, user, conversation_id, body.body)
    out = service.message_out(message, user)
    await session.commit()
    return out
