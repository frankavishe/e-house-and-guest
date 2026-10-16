# REST API Contract: Rental Marketplace MVP

Base path `/api/v1`, JSON, served by FastAPI. The OpenAPI document at `/api/v1/openapi.json`
is the source of truth once built. This file is the design contract it must match, and
contract tests (schemathesis + per-endpoint tests) enforce it.

## Conventions

- **Auth**: httpOnly cookies `access_token` (15 min) and `refresh_token` (30 d). Endpoints
  are marked 🌐 public, 👤 signed in, 🏠 owner (verified owner where noted), 🛡 admin.
- **Language**: `Accept-Language: sw|en` (default `sw`) picks the localized fields and error
  messages.
- **Money**: integers in TZS, field suffix `_tzs`. **Time**: ISO 8601 with offset, and dates
  as `YYYY-MM-DD` in EAT.
- **Pagination**: `?page=1&page_size=20` (max 50) → `{items, page, page_size, total}`.
- **Errors**: `{"error": {"code": "SLOT_TAKEN", "message": "<localized>", "details": {...}}}`.
  Codes include `VALIDATION_ERROR` 422, `UNAUTHENTICATED` 401, `FORBIDDEN` 403,
  `NOT_FOUND` 404, `SLOT_TAKEN` 409, `INSUFFICIENT_STOCK` 409 (`details.available`),
  `INVALID_TRANSITION` 409, `OTP_INVALID` 400, `RATE_LIMITED` 429, `OWN_LISTING` 422,
  `OUTSIDE_DELIVERY_AREA` 422.
- **Idempotency**: `POST /bookings` and `POST /bookings/{id}/payments` accept an
  `Idempotency-Key` header. A replay within 24 h returns the original response.

## Common schemas

```text
Money          = integer (TZS)
Localized      = { "sw": string, "en": string }
PeriodInput    = one of, by booking mode:
  DATE_RANGE   { "start_date": date, "end_date": date }          # nights: end = check-out; days: end inclusive
  TIME_SLOT    { "start": datetime, "end": datetime }
  LEASE        { "start_date": date, "months": int }
  QUANTITY     { "start_date": date, "end_date": date, "quantity": int }
Quote          = { lines: [{label, unit, count, unit_price_tzs, amount_tzs}], rental_tzs,
                   delivery_fee_tzs, service_fee_tzs, deposit_tzs, total_tzs }
ListingCard    = { id, title, category:{id,slug,name}, location:{region,district},
                   cover_photo:{url_320,url_640,alt}, base_price:{unit,amount_tzs},
                   total_tzs?, rating_avg, rating_count, instant_book, lat?, lng? }
```

---

## Auth & profile

| Method | Path | Access | Request → Response |
|---|---|---|---|
| POST | `/auth/otp/request` | 🌐 | `{phone}` → `202 {expires_in: 300}`; 429 after 3 per 15 min |
| POST | `/auth/otp/verify` | 🌐 | `{phone, code}` → `200 {user, is_new}` + sets cookies |
| POST | `/auth/refresh` | 🌐 (cookie) | → `204` rotated cookies |
| POST | `/auth/logout` | 👤 | → `204` revokes refresh family |
| GET | `/me` | 👤 | → `User {id, phone, name, email, language, roles[], owner_profile?}` |
| PATCH | `/me` | 👤 | `{name?, email?, language?}` → `User` |
| DELETE | `/me` | 👤 | → `202` anonymisation scheduled (FR-033); 409 if active bookings |

## Owner onboarding & payouts setup

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/owner-profile` | 👤 | `{kind, display_name, nida_number? \| business_name, brela_reg_no, tin}` → `OwnerProfile` (status `draft`) |
| PATCH | `/owner-profile` | 🏠 | edit while `draft`/`rejected` |
| POST | `/owner-profile/documents` | 🏠 | → `{upload_url, storage_key}` presigned PUT (private bucket) |
| POST | `/owner-profile/submit` | 🏠 | `draft\|rejected → pending` |
| GET/POST | `/owner-profile/payout-methods` | 🏠 | list / add `{kind, network?, msisdn?, bank_name?, account_name, account_number?}` |
| DELETE | `/owner-profile/payout-methods/{id}` | 🏠 | |

## Catalogue (public)

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/categories` | 🌐 | full tree `[{id, slug, name, booking_mode?, price_units, children[]}]`; cacheable 5 min |
| GET | `/categories/{slug}` | 🌐 | + `attribute_schema` (drives forms and filters) |
| GET | `/locations?parent_id=&level=` | 🌐 | regions, districts or wards |

## Search & listing detail

`GET /listings/search` 🌐

| Param | Type | Notes |
|---|---|---|
| `category` | slug | includes subtree |
| `region`, `district`, `ward` | int | |
| period params | as `PeriodInput`, flattened | availability + `total_tzs` only when given |
| `q` | string | text search |
| `price_min`, `price_max` | int | on base price |
| `attr.<key>` | value | `attr.vehicle_type=4x4`, `attr.with_driver=true`; ranges: `attr.bedrooms.min=2` |
| `bbox` | `minLng,minLat,maxLng,maxLat` | map view |
| `sort` | `price_asc`,`price_desc`,`rating`,`newest` | default `newest` |

→ `Page<ListingCard>` with `total_tzs` filled when a period is supplied. Unknown `attr.*`
keys → 422.

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/listings/{id}` | 🌐 | `ListingDetail`: card fields + descriptions, all photos, attributes with labels, prices, deposit, delivery, policies, owner `{display_name, rating, verified}`, recent reviews. No phone or exact address. |
| GET | `/listings/{id}/availability?from=&to=` | 🌐 | DATE_RANGE/LEASE: unavailable date ranges; TIME_SLOT: free slots per day; QUANTITY: `[{date, available}]` |
| POST | `/listings/{id}/quote` | 🌐 | `PeriodInput + {delivery?: bool, delivery_district_id?}` → `Quote` or 409/422 |

## Owner listing management 🏠

| Method | Path | Notes |
|---|---|---|
| GET | `/owner/listings` | own listings, any status |
| POST | `/owner/listings` | `{category_id}` → draft |
| PATCH | `/owner/listings/{id}` | any listing fields; `attributes` validated against the category schema (422 with per-field errors) |
| POST | `/owner/listings/{id}/photos` | → presigned PUT; then `PATCH .../photos/{pid}` to confirm/order/alt |
| DELETE | `/owner/listings/{id}/photos/{pid}` | |
| PUT | `/owner/listings/{id}/prices` | replace the full price list `[{unit, amount_tzs, season_start?, season_end?}]` |
| POST | `/owner/listings/{id}/submit` | → `pending_review`; requires verified owner (or queued until verified), ≥1 photo, ≥1 price |
| POST | `/owner/listings/{id}/pause` · `/resume` | |
| DELETE | `/owner/listings/{id}` | soft delete; 409 if future confirmed bookings |
| GET/POST | `/owner/listings/{id}/blocks` | owner blocks `{start, end, quantity?, note?}` (US3-AS3) |
| DELETE | `/owner/listings/{id}/blocks/{bid}` | |
| GET | `/owner/calendar?from=&to=` | bookings and blocks across own listings |

## Bookings

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/bookings` | 👤 | `{listing_id, period: PeriodInput, delivery?, delivery_address?, message?}` → `201 Booking`. Status `awaiting_payment` (instant, `payment_due_at` +15 min) or `requested`. Errors: `SLOT_TAKEN`, `INSUFFICIENT_STOCK {available}`, `OWN_LISTING`, duration limits. |
| GET | `/bookings?role=renter\|owner&status=` | 👤 | `Page<BookingSummary>` |
| GET | `/bookings/{id}` | 👤 party / 🛡 | `Booking` incl. quote, events, payments, installments; counterpart phone and address only if `confirmed` or later |
| POST | `/bookings/{id}/accept` | 🏠 owner | `requested → awaiting_payment`, `payment_due_at` +24 h |
| POST | `/bookings/{id}/decline` | 🏠 owner | `{reason?}` → `cancelled` |
| POST | `/bookings/{id}/cancel` | 👤 party | `{reason?}` → `cancelled` + `refund_preview` applied per policy (owner cancel = full) |
| GET | `/bookings/{id}/cancel-preview` | 👤 party | → `{refund_tzs, policy, deadline}` |
| POST | `/bookings/{id}/claims` | 👤 party | `{kind, description, amount_claimed_tzs?, evidence_keys[]}`; damage only ≤ 48 h after end |

`Booking = { id, code, status, listing: ListingCard, period, quantity, quote: Quote,
payment_due_at?, request_expires_at?, cancellation_policy, can: {pay, cancel, accept,
decline, review, claim}, counterpart: {name, phone?}, events: [...], payments: [...],
installments?: [...] }`

## Payments

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/bookings/{id}/payments` | 👤 renter | `{network, msisdn, installment_id?}` → `202 Payment {id, status: pending}`; triggers USSD push. 409 if not `awaiting_payment` or a payment is already pending. |
| GET | `/payments/{id}` | 👤 renter | `{status, failure_reason?}`. The UI polls every 3 s (no websockets). Also forces a provider status check if pending > 60 s. |
| POST | `/webhooks/payments/{provider}/{secret}` | provider | Raw callback. Always `200` once stored; processing per research R6. Not in public OpenAPI client. |
| GET | `/bookings/{id}/receipt` | 👤 party | receipt JSON (rendered as a page and SMS) |

## Earnings & payouts 🏠

| Method | Path | Notes |
|---|---|---|
| GET | `/owner/earnings?from=&to=` | `{totals: {gross_tzs, commission_tzs, net_tzs, paid_out_tzs, pending_tzs}, items: [{booking_code, gross, commission, net, status}]}` (US4-AS1) |
| GET | `/owner/payouts` | `Page<Payout {amount_tzs, status, provider_ref, paid_at, items}>` |

## Messaging & reviews 👤

| Method | Path | Notes |
|---|---|---|
| POST | `/conversations` | `{listing_id, body}` → conversation (renter starts; reuses existing) |
| GET | `/conversations` | inbox with unread counts |
| GET | `/conversations/{id}/messages?after=` | polling (every 10 s while open) |
| POST | `/conversations/{id}/messages` | `{body}`; phones masked pre-confirmation |
| POST | `/bookings/{id}/reviews` | `{rating 1–5, body?}`; 403 unless `completed` party; 409 if already reviewed |
| GET | `/listings/{id}/reviews` · `/users/{id}/reviews` | 🌐 |
| POST | `/reports` | `{target_kind, target_id, reason}` (FR-030) |
| GET | `/notifications` · POST `/notifications/read` | in-app notification feed |

## Admin 🛡

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/owner-verifications?status=pending` | with presigned document links (5 min) |
| POST | `/admin/owner-verifications/{id}/approve` · `/reject {reason}` | US7-AS2 |
| GET | `/admin/listings?status=pending_review` | with diff vs last approved version |
| POST | `/admin/listings/{id}/approve` · `/reject {reason}` · `/suspend {reason}` · `/unsuspend` | |
| GET/POST | `/admin/categories` | create `{parent_id, slug, name, booking_mode, price_units, default_unit, attribute_schema, commission_bps, renter_fee_bps}` |
| PATCH | `/admin/categories/{id}` | edit, incl. schema (validated; type changes on fields in use → 409) |
| GET | `/admin/bookings?status=&q=` · `/admin/bookings/{id}` | |
| POST | `/admin/bookings/{id}/cancel` · `/refund {amount_tzs, reason}` | |
| GET | `/admin/claims?status=open` · POST `/admin/claims/{id}/resolve {resolution, amount_awarded_tzs}` | |
| GET | `/admin/reports-abuse` · POST `/admin/reports-abuse/{id}/action` | |
| POST | `/admin/users/{id}/suspend` · `/unsuspend` | |
| GET | `/admin/payouts?status=` · POST `/admin/payouts/{id}/mark-paid {provider_ref}` · `/retry` | manual fallback (R7) |
| GET | `/admin/stats?from=&to=&group_by=category\|region\|month` | `{bookings, gbv_tzs, commission_tzs, refunds_tzs, payouts_tzs}` rows (FR-032); `?format=csv` |

## Health

`GET /health` 🌐 → `{status: "ok", db: "ok"}`.
