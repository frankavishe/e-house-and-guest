# Research: Rental Marketplace MVP

**Feature**: `001-rental-marketplace-mvp` | **Date**: 2026-10-16 | **Plan**: [plan.md](plan.md)

Each entry records a decision, why it was chosen and what was rejected. Items that need a
real-world check before go-live are marked **Verify**.

---

## R1. Preventing double booking (Principle IV, FR-015, SC-003)

**Decision**: Two mechanisms, chosen by booking mode, both inside the booking-creation
transaction.

- `DATE_RANGE`, `TIME_SLOT`, `LEASE` (exclusive use): every booking hold and owner block
  writes a row in `availability_blocks` with a `tstzrange` period. A PostgreSQL **exclusion
  constraint** (`btree_gist`: `listing_id WITH =, period WITH &&`, filtered on
  `kind = 'exclusive' AND active`) makes an overlapping insert fail at the database level,
  however many API workers race. The losing request gets `409 SLOT_TAKEN`.
- `QUANTITY` (stock): the transaction runs `SELECT … FROM listings WHERE id = :id FOR UPDATE`.
  It then sums the active quantity blocks that overlap each requested day, checks
  `booked + requested <= stock` and inserts the block. The listing-row lock serialises
  concurrent bookings of one item. Other listings are unaffected.

**Rationale**: Exclusion constraints are race-proof without application locks. The stock
check needs arithmetic that a constraint cannot express, and one row lock per listing is
cheap at MVP scale.

**Alternatives rejected**: Redis distributed locks (extra infrastructure, Principle VII).
`SERIALIZABLE` isolation everywhere (retry storms, harder to reason about). A per-day
inventory table (`listing_id, day, booked_qty CHECK <= stock`) is correct but needs a row
written per day per booking. Keep it in reserve if stock contention becomes a hotspot.

## R2. Time representation

**Decision**: Store every instant as `timestamptz` (UTC). Business rules run in
`Africa/Dar_es_Salaam` (EAT, UTC+3, no DST). Each mode maps to a half-open `tstzrange`:

| Mode | Renter input | Stored period |
|---|---|---|
| DATE_RANGE (nights) | check-in, check-out dates | `[check_in 00:00 EAT, check_out 00:00 EAT)` (check-out day is free) |
| DATE_RANGE (days, e.g. vehicles) | first day, last day | `[first 00:00, last+1 00:00)` |
| TIME_SLOT | date + start/end time | `[start, end)`; may cross midnight |
| LEASE | start date + months | `[start, start + n months)` |
| QUANTITY | first/last day + qty | `[first 00:00, last+1 00:00)` + `quantity` |

Whether a DATE_RANGE category counts nights or days is a category setting
(`price_unit_default = night|day`), so no code branches on category (Principle I).

## R3. Category attribute schemas (Principle I, FR-006, SC-006)

**Decision**: `categories.attribute_schema` holds a JSON array of field definitions (format
in [contracts/attribute-schema.md](contracts/attribute-schema.md)). The backend validates
`listings.attributes` against it at write time by building a Pydantic model dynamically
from the schema (cached per category version). Search filters come from the same schema:
`enum`/`bool` filters use `attributes @> '{"k": v}'` on a GIN (`jsonb_path_ops`) index, and
numeric range filters use `(attributes->>'k')::numeric`. The frontend renders the listing
form and the filter panel from the schema, so a new rental type needs no code change.

**Alternatives rejected**: EAV tables (slow, awkward queries), per-type tables (forbidden
by Principle I), JSON Schema + `jsonschema` library (fine, but a smaller in-house field
format is simpler for admins to edit and maps directly to form widgets and filters).

## R4. Search and maps

**Decision**: Plain PostgreSQL. The query combines a category subtree (materialised `path`
column), a location filter (region/district/ward ids), attribute filters, a price range
on the listing's base price, and availability:
`NOT EXISTS (overlapping exclusive block)`, or for QUANTITY a stock subquery. Map view
uses `lat`/`lng` numeric columns with a bounding-box filter and a btree index. Results are
paginated (20) and sorted by base price, rating or newest. The total for the requested
period is computed by the pricing service for the returned page only. Text search uses a
generated `tsvector` (simple config, sw+en titles).

**Rationale**: Expected MVP scale (≤ 50k listings) fits comfortably in Postgres. SC-002
(< 2 s on 3G) is dominated by payload size, which is addressed by server rendering and
small responses.

**Alternatives rejected**: Elasticsearch/Meilisearch (extra infrastructure), PostGIS (bbox
is enough for now; easy to add later).

## R5. Pricing

**Decision**: `listing_prices` rows `(unit, amount_tzs, season_start?, season_end?)`. The
pricing service splits the requested period into units (nights/days/hours/months/item-days).
Each unit is priced at the matching seasonal rate, or the base rate if none matches. Weekly
rates apply to whole weeks when they are cheaper. The service then adds delivery, the
service fee (`category.renter_fee_bps`) and the deposit. All amounts are `bigint` TZS and
percentages are basis points, rounded half-up to whole shillings. The quote is
**snapshotted** onto the booking when it is created, so later price edits do not affect it
(edge case "owner edits prices while renter is in checkout").

## R6. Payments: AzamPay first, behind `PaymentProvider` (Principle III, FR-021/022)

**Decision**: A `PaymentProvider` protocol ([contracts/providers.md](contracts/providers.md))
with `AzamPayProvider` and `MockProvider`. Checkout uses AzamPay **MNO checkout**
(`POST /azampay/mno/checkout`, providers `Mpesa`, `Tigo` (Mixx by Yas), `Airtel`,
`Halopesa`, plus `Azampesa`), which sends a USSD push and returns a transaction id. The
result arrives asynchronously by callback.

Callback safety:
1. Callback URL contains an unguessable per-environment secret path segment, and the
   request must carry the callback password configured in the AzamPay portal.
2. The callback is stored raw in `payment_events` with a unique `(provider, provider_event_id)`.
   A duplicate insert is a no-op, which makes callbacks idempotent.
3. The handler **re-queries the transaction status** from AzamPay before changing state. The
   callback is only a trigger and is never trusted alone.
4. State changes use `UPDATE payments SET status='succeeded' WHERE id=:id AND status='pending'`,
   so a second success cannot double-confirm. A success that arrives after the hold expired
   triggers re-reservation if the slot is still free, otherwise an automatic refund (edge case).

A reconciliation job polls `pending` payments older than 2 minutes, which covers lost
callbacks and the "network loss during payment" edge case.

**Verify**: Official schemas, the callback payload and the exact callback authentication
are at `developerdocs.azampay.co.tz` and could not be confirmed from public sources. Check
them against the AzamPay sandbox before building `AzamPayProvider`. Third-party SDKs disagree
on what the disbursement endpoint does, so confirm that wallet and bank payouts are
supported (R7).

**Alternatives considered**: Selcom, ClickPesa, DPO, and direct per-MNO integrations
(4 contracts, 4 APIs). The interface keeps a switch open.

## R7. Payouts (FR-024, SC-008)

**Decision**: Payouts go through `PayoutProvider.disburse()`. AzamPay is used if its
disbursement API supports TZ wallets and banks, otherwise an admin "mark paid manually"
flow with a reference is used. A daily job groups each owner's available ledger balance
(bookings completed ≥ 24 h ago, no open dispute) into one `payout`. The manual fallback keeps
SC-008 (initiated within 48 h) achievable even before the disbursement API is live.

## R8. Money ledger (Principle III, FR-025)

**Decision**: Append-only, double-entry `ledger_entries`. Each money event writes balanced
rows (sum = 0) across accounts: `renter_clearing`, `platform_revenue`, `owner_payable:{owner}`,
`deposit_held`, `provider_cash`. Balances are `SUM(amount)` views and are never stored. Rows
are never updated or deleted, and corrections are new reversing entries. A DB trigger
rejects `UPDATE/DELETE` on the table.

## R9. Background work without new infrastructure (Principle VII)

**Decision**: One **worker process** from the same codebase, backed by a Postgres `jobs`
table (`SELECT … FOR UPDATE SKIP LOCKED`) plus a scheduler loop for periodic sweeps:
- expire holds (15 min instant, 24 h after approval) and undecided requests (24 h)
- booking status transitions (confirmed → in_progress → completed)
- deposit auto-refund 48 h after end
- lease installment billing and reminders
- payment reconciliation, payouts, outgoing SMS, image resizing

Every job is idempotent and safe to re-run. **Alternatives rejected**: Celery + Redis (extra
broker), APScheduler inside the API process (duplicate runs with several API workers). The
worker is recorded in Complexity Tracking.

## R10. Authentication (FR-001, constitution Security)

**Decision**: Phone + 6-digit OTP. The code is hashed (HMAC-SHA256) and valid for 5 minutes,
with at most 5 attempts per code and 3 sends per phone per 15 minutes. Phones are normalised
to E.164 `+255XXXXXXXXX`. The JWT access token lasts 15 minutes. The refresh token lasts 30 days,
rotates on use and is stored hashed with reuse detection. Tokens live in **httpOnly,
Secure, SameSite=Lax cookies**. The browser talks to the API through a Next.js rewrite
(`/api/*` → FastAPI), so everything is same-origin and needs no CORS. Server components
forward the cookie when calling the API. Roles: `renter` (everyone), `owner` (after creating an
owner profile), `admin`.

## R11. SMS and OTP delivery

**Decision**: `SmsProvider` interface with `BeemSmsProvider` (Beem Africa, a Tanzanian
provider with a registered sender ID) and a `ConsoleSmsProvider` for dev and tests. The
sender ID and templates must be registered with the provider and TCRA in advance (lead time).
Messages are queued through the `jobs` table (outbox pattern), so an SMS failure never rolls
back a booking. **Verify**: sender-ID approval timeline and per-SMS cost.

## R12. File storage and images (Principle VI)

**Decision**: `StorageProvider` targets S3-compatible storage (MinIO locally; any S3/R2 in
production). The browser uploads directly via presigned PUT (≤ 10 MB, jpeg/png/webp). The
worker generates WebP variants (320, 640, 1280 px) with Pillow and strips EXIF/GPS. Pages
use `next/image`-style `srcset` with explicit sizes and alt text, so layouts hold when images
fail. Verification documents go to a **private** bucket and are only reachable through
short-lived presigned GETs for admins.

## R13. Internationalisation (Principle II, SC-007)

**Decision**:
- Frontend: `next-intl`, locale prefix `/sw` (default) and `/en`, catalogs
  `frontend/messages/{sw,en}.json`. A CI test fails if the key sets differ.
- Backend: SMS and notification templates in `backend/app/i18n/{sw,en}.json`, rendered in the
  recipient's `users.language`, with the same parity test.
- User content: listings have `title_sw/title_en`, `description_sw/description_en`, and at
  least one is required. Display falls back to the other language.
- Categories and attribute labels/options carry `{sw, en}` objects, and admin forms require both.
- Number and currency formatting: `TSh 1,250,000` via `Intl.NumberFormat`, no decimals.

## R14. Frontend architecture (Principles VI, VII)

**Decision**: Next.js App Router + TypeScript. Server components are the default, and client
components are limited to the booking widget, image uploader, map and admin tables.
Tailwind CSS. The typed API client comes from the backend OpenAPI via `openapi-typescript`
+ `openapi-fetch`, regenerated by `npm run gen:api`. Leaflet + OSM tiles load only on the
map view (`dynamic(..., {ssr:false})`). JS budget: ≤ 300 KB gz initial per route, checked by
`@next/bundle-analyzer` in CI. Admin is a section of the same app (`/[locale]/admin`)
guarded by role, not a separate app.

## R15. Testing strategy (Principle V)

**Decision**:
- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` against a real Postgres (docker
  compose `db-test`). Each test runs in a transaction that rolls back. Concurrency tests open
  separate connections and use `asyncio.gather`, with N=20 attempts on the same slot and stock
  for each mode.
- Contract tests: `schemathesis` against the generated OpenAPI, plus explicit
  request/response tests per endpoint group.
- Test-first modules: availability, pricing, booking state machine, payments/webhooks,
  ledger, authorization.
- Frontend: Vitest for utilities, and Playwright smoke tests for search → book → pay with
  the mock provider, at a 360×640 viewport.
- Tooling: `uv` (deps), `ruff` (lint/format), `mypy --strict` on `app/`, ESLint + `tsc`.

## R16. Location data

**Decision**: `locations` is a self-referencing table (region → district → ward) seeded from
a CSV in `backend/seed/locations.csv` built from the NBS 2022 census administrative units.
All 31 regions (incl. Zanzibar) and all districts ship at launch. Wards ship for the five
launch cities first, and the rest are added by later seed runs without code change.
**Verify**: dataset licence and currency.

## R17. Booking lifecycle

**Decision**: An explicit state machine in `bookings/state.py`, as a transition table with
guards. Every transition writes `booking_events` and enqueues notifications:

```
requested ──accept──▶ awaiting_payment ──pay ok──▶ confirmed ──start──▶ in_progress ──end──▶ completed
    │                      │                          │                    │
    ├─decline/expire──▶ cancelled ◀──expire──┘        ├─cancel──▶ cancelled │
                                                      └──────dispute────────┴──▶ disputed ──resolve──▶ completed|cancelled
instant book: (new) ──▶ awaiting_payment
```
LEASE bookings stay `in_progress` across months, and each `lease_installment` has its own
payment. A missed installment after 7 days notifies the owner and admin. Termination is
handled manually by an admin in the MVP.

## R18. Privacy (FR-033, PDPA 2022)

**Decision**: Account deletion anonymises the user (name → "Deleted user", phone → hashed
tombstone, email null), deletes verification files and messages, and keeps bookings and
ledger rows (financial retention). NIDA/TIN numbers are encrypted at rest (Fernet key from
env). A log filter masks phone and ID patterns. Phone numbers are revealed to the other party
only on `confirmed` bookings. Messages sent before confirmation have phone-like numbers masked.

## R19. Hosting (open, not blocking)

Deployment target is not decided. The plan assumes Linux containers (API, worker, web) +
managed Postgres 16 + S3-compatible storage, in a region with low latency to Tanzania
(e.g. a South Africa or Europe cloud region, or a local Tanzanian data centre if PDPA
data-localisation guidance requires it). **Verify** PDPA cross-border transfer rules before
choosing.
