"""Availability responses (`GET /listings/{id}/availability`)."""

from datetime import date, datetime

from pydantic import BaseModel

from app.catalog.schemas import BookingModeT


class DateSpan(BaseModel):
    """Unavailable EAT days `[start_date, end_date)`."""

    start_date: date
    end_date: date


class DayStock(BaseModel):
    date: date
    available: int


class Slot(BaseModel):
    start: datetime
    end: datetime


class DaySlots(BaseModel):
    date: date
    slots: list[Slot]


class Availability(BaseModel):
    """DATE_RANGE/LEASE fill `unavailable`, TIME_SLOT `slots`, QUANTITY `stock`."""

    booking_mode: BookingModeT
    unavailable: list[DateSpan] | None = None
    slots: list[DaySlots] | None = None
    stock: list[DayStock] | None = None
