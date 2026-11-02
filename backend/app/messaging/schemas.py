import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.listings.schemas import Page
from app.messaging.models import MESSAGE_MAX

Body = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX)
]


class ConversationStart(BaseModel):
    listing_id: uuid.UUID
    body: Body


class MessageIn(BaseModel):
    body: Body


class ConversationListing(BaseModel):
    id: uuid.UUID
    title: str
    photo_url: str | None


class ConversationParty(BaseModel):
    name: str


class ConversationOut(BaseModel):
    """`role` is the viewer's side; `booking_id` is set once a booking reveals phones."""

    id: uuid.UUID
    listing: ConversationListing
    role: Literal["renter", "owner"]
    counterpart: ConversationParty
    booking_id: uuid.UUID | None
    last_message: str | None
    last_message_at: datetime | None
    unread_count: int


class Inbox(Page[ConversationOut]):
    unread_total: int


class MessageOut(BaseModel):
    """`seq` is the polling cursor; `masked`: phone numbers were hidden (R18)."""

    id: uuid.UUID
    seq: int
    mine: bool
    body: str
    masked: bool
    read_at: datetime | None
    created_at: datetime


class MessageList(BaseModel):
    items: list[MessageOut]


AfterParam = Annotated[int, Field(ge=0, le=2**62)]
