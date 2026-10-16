# Contract: External Provider Interfaces

All external services sit behind Python protocols in `backend/app/integrations/`, with a
local or mock implementation used in development and tests (Principle VII). They are picked
by environment variable (`PAYMENT_PROVIDER=mock|azampay`, `SMS_PROVIDER=console|beem`,
`STORAGE_PROVIDER=local|s3`).

## PaymentProvider

```python
class PaymentProvider(Protocol):
    name: str

    async def start_checkout(self, *, payment_id: UUID, amount_tzs: int,
                             msisdn: str, network: Network) -> CheckoutStarted:
        """Send USSD push. Returns provider_txn_id. Must not raise on user-side failure;
        raises ProviderUnavailable on transport errors (caller marks payment failed/retry)."""

    async def get_status(self, *, payment_id: UUID,
                         provider_txn_id: str | None) -> PaymentStatus:
        """Authoritative status query. Used after every callback and by reconciliation."""

    def parse_callback(self, *, headers: Mapping[str, str], body: bytes) -> CallbackEvent:
        """Authenticate (callback secret/password) and parse. Raises InvalidCallback.
        Returns provider_event_id (for idempotency), payment_id/provider_txn_id, claimed status."""

    async def refund(self, *, payment_id: UUID, amount_tzs: int, msisdn: str,
                     network: Network) -> RefundResult: ...

class PayoutProvider(Protocol):
    async def disburse(self, *, payout_id: UUID, amount_tzs: int,
                       destination: PayoutDestination) -> PayoutResult: ...
    async def get_payout_status(self, *, payout_id: UUID, provider_ref: str) -> PayoutStatus: ...
```

`Network = mpesa | mixx | airtel | halopesa | azampesa`. AzamPay mapping: `Mpesa`, `Tigo`,
`Airtel`, `Halopesa`, `Azampesa`.

### Callback handling contract (Principle III)

1. `POST /api/v1/webhooks/payments/{provider}/{secret}`: a wrong secret returns 404.
2. `parse_callback` authenticates. Failure → 401, logged without PII.
3. Insert into `payment_events` (unique `provider, provider_event_id`). On conflict → return 200
   and do nothing more.
4. `get_status` → if `succeeded`, a guarded update `pending → succeeded` runs in one transaction
   with: booking `awaiting_payment → confirmed`, ledger entries, notification jobs.
5. Return 200 within 5 s. Heavy work (SMS) is queued.

### MockProvider behaviour (dev/tests)

- `msisdn` ending `…0001` → succeeds after 2 s; `…0002` → fails (`insufficient_funds`);
  `…0003` → never calls back (tests reconciliation and expiry); `…0004` → calls back twice
  (tests idempotency). Any other number succeeds.
- `POST /api/v1/dev/mock-payments/{payment_id}/{succeed|fail}` is available only when
  `ENV=dev|test`.

## SmsProvider

```python
class SmsProvider(Protocol):
    async def send(self, *, to: str, text: str) -> SmsResult  # provider message id
```
Texts are rendered from `app/i18n/{sw,en}.json` in the recipient's language and kept to
≤ 160 GSM-7 characters where possible. `ConsoleSmsProvider` logs to stdout, and in `test` it
stores messages in memory so tests can read OTP codes.

## StorageProvider

```python
class StorageProvider(Protocol):
    def presign_put(self, *, key: str, content_type: str, max_bytes: int, private: bool) -> PresignedPut
    def presign_get(self, *, key: str, ttl_s: int) -> str
    def public_url(self, *, key: str) -> str
    async def get(self, key: str) -> bytes
    async def put(self, key: str, data: bytes, content_type: str, private: bool) -> None
```

## Map tiles

Frontend only: Leaflet with the OpenStreetMap tile URL from `NEXT_PUBLIC_TILE_URL`, with
attribution shown. No geocoding API in the MVP: owners drop a pin, and the region, district
and ward are picked from lists.
