"""Manual payouts (R7 fallback): nothing is sent automatically. The payout stays `pending`
with its destination snapshot until an admin sends the money and marks it paid with the
transfer reference (`POST /admin/payouts/{id}/mark-paid`)."""

import uuid

from app.integrations.payments.base import PayoutDestination, PayoutResult, PayoutStatus


class ManualPayoutProvider:
    name = "manual"

    async def disburse(
        self, *, payout_id: uuid.UUID, amount_tzs: int, destination: PayoutDestination
    ) -> PayoutResult:
        return PayoutResult(state="pending")

    async def get_payout_status(self, *, payout_id: uuid.UUID, provider_ref: str) -> PayoutStatus:
        return PayoutStatus(state="pending")
