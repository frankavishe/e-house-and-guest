"""Quote shapes (contracts/rest-api.md "Common schemas")."""

from typing import Literal

from pydantic import BaseModel

UnitT = Literal["hour", "night", "day", "week", "month", "item_day"]


class QuoteLine(BaseModel):
    """`label` is `base` or `season` (a seasonal rate); clients localize it."""

    label: Literal["base", "season"]
    unit: UnitT
    count: int
    unit_price_tzs: int
    amount_tzs: int


class Quote(BaseModel):
    lines: list[QuoteLine]
    rental_tzs: int
    delivery_fee_tzs: int
    service_fee_tzs: int
    deposit_tzs: int
    total_tzs: int
