# Data Model: Rental Marketplace MVP

**Feature**: `001-rental-marketplace-mvp` | **Date**: 2026-10-16 | **Research**: [research.md](research.md)

PostgreSQL 16, extensions `btree_gist`, `pgcrypto`. All ids are `uuid` (v7, generated in
app) unless noted. All money columns are `bigint` TZS (`_tzs` suffix) and percentages are
basis points (`_bps`, 1000 = 10%). All instants are `timestamptz` (UTC) and business rules
use EAT. Every table has `created_at`, and mutable tables also have `updated_at`.

## Entity overview

```
users ─┬─< owner_profiles ──< payout_methods
       │        └──< listings >── categories (tree) ── attribute_schema (JSONB)
       │               ├──< listing_photos
       │               ├──< listing_prices
       │               ├──< availability_blocks >── bookings
       │               └── locations (region > district > ward)
       ├──< bookings ─┬──< booking_events
       │              ├──< payments ──< payment_events
       │              ├──< lease_installments
       │              ├──< refunds
       │              ├──< claims (damage / dispute)
       │              └──< reviews
       ├──< conversations ──< messages
       ├──< notifications
       └──< reports (abuse)
ledger_entries ─> bookings / payments / refunds / payouts
payouts ──< payout_items >── bookings
jobs (worker queue) · otp_codes · refresh_tokens · admin_audit_log
```

---

## Accounts & identity

### users
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| phone | text UNIQUE NOT NULL | E.164 `+255[67]\d{8}`; normalised on input |
| name | text | required before first booking or listing |
| email | citext UNIQUE NULL | optional |
| language | enum `sw`,`en` | default `sw` (FR-004) |
| is_admin | bool | default false |
| status | enum `active`,`suspended`,`deleted` | `deleted` = anonymised (R18) |
| owner_cancellation_count | int | default 0 (US5-AS2) |
| rating_avg / rating_count | numeric(3,2) / int | denormalised from reviews (as renter) |

Roles (FR-002): renter = any active user; owner = has `owner_profiles` row; admin = `is_admin`.

### otp_codes
`id, phone, code_hash, purpose (login), expires_at (+5 min), attempts (≤5), consumed_at`.
Index `(phone, created_at)` for the rate limit (3 per 15 min).

### refresh_tokens
`id, user_id, token_hash UNIQUE, family_id, expires_at, revoked_at, replaced_by`. Reuse of a
revoked token revokes the whole family.

### owner_profiles
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK UNIQUE | one per user |
| kind | enum `individual`,`business` | |
| display_name | text | shown publicly |
| nida_number_enc | bytea NULL | required if individual; Fernet-encrypted |
| business_name, brela_reg_no | text NULL | required if business |
| tin_enc | bytea NULL | required if business |
| documents | jsonb | list of private storage keys (ID scan, certificate) |
| verification_status | enum `draft`,`pending`,`verified`,`rejected` | |
| rejection_reason | text NULL | required when `rejected` (US7-AS2) |
| verified_at, verified_by | | |
| rating_avg / rating_count | | as owner |

Transitions: `draft → pending` (owner submits) → `verified | rejected` (admin);
`rejected → pending` (resubmit). Listings are searchable only if the owner is `verified`.

### payout_methods
`id, owner_profile_id, kind (mobile_money|bank), network (mpesa|mixx|airtel|halopesa) NULL,
msisdn NULL, bank_name NULL, account_name, account_number_enc NULL, is_default`. Exactly one
default per owner (partial unique index).

---

## Catalogue

### locations
`id int PK, parent_id FK NULL, level enum(region,district,ward), name, slug, lat, lng`.
Unique `(parent_id, slug)`. Seeded (R16).

### categories
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| parent_id | uuid FK NULL | top level = one of the 6 groups |
| path | ltree-like text | e.g. `accommodation.guest-houses`, for subtree search |
| slug | text UNIQUE | |
| name | jsonb `{sw,en}` | both required |
| booking_mode | enum `DATE_RANGE`,`TIME_SLOT`,`LEASE`,`QUANTITY` | required on leaf categories |
| price_units | text[] | allowed units, e.g. `{night,week,month}` |
| default_unit | text | e.g. `night` vs `day` decides night/day counting (R2) |
| attribute_schema | jsonb | see [contracts/attribute-schema.md](contracts/attribute-schema.md) |
| schema_version | int | bumped on every schema edit |
| commission_bps | int | default 1000 (FR-023) |
| renter_fee_bps | int | default 0 |
| is_active | bool | |
| sort_order | int | |

Only leaf categories can hold listings. Removing a field from a schema keeps existing values,
which are ignored for display and filtering. Changing a field's type is refused if listings
have values for it.

### listings
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| owner_profile_id | uuid FK | |
| category_id | uuid FK (leaf) | |
| title_sw, title_en | text NULL | at least one; ≤ 120 chars |
| description_sw, description_en | text NULL | at least one; ≤ 5000 chars |
| attributes | jsonb | validated against the category schema (R3); GIN `jsonb_path_ops` |
| region_id, district_id, ward_id | int FK | district required; ward optional |
| address_hint | text NULL | shown after booking confirmed |
| lat, lng | numeric(9,6) NULL | btree `(lat, lng)` |
| stock | int | `>= 1`; meaningful only for QUANTITY (1 otherwise) |
| deposit_tzs | bigint | `>= 0` |
| delivery | enum `none`,`optional`,`required` | |
| delivery_fee_tzs | bigint NULL | |
| delivery_area | text[] NULL | district ids served |
| min_duration, max_duration | int NULL | in `default_unit` |
| slot_config | jsonb NULL | TIME_SLOT only: `{open:"08:00", close:"22:00", slot_minutes:60, days:[1..7]}` |
| cancellation_policy | enum `flexible`,`moderate`,`strict` | FR-026 |
| instant_book | bool | always false for LEASE |
| base_price_tzs | bigint | denormalised default-unit price for sorting and filtering |
| status | enum below | |
| rejection_reason | text NULL | |
| search_tsv | tsvector GENERATED | from titles |
| rating_avg / rating_count | | |

Status transitions (FR-007, FR-009, FR-030):
```
draft → pending_review → active ⇄ paused
              ↓                ↓
           rejected → (edit) pending_review
active/paused → suspended (admin) → active (admin)
any → deleted (soft; refused if future confirmed bookings exist)
```
A **material edit** of an `active` listing moves it back to `pending_review` and keeps it
bookable under its last approved version until a decision. Material edits are changes to
title, description, category, attributes, photos or location. Price-only edits do not
need review. Suspending a listing with future confirmed bookings is allowed: those bookings
are flagged for admin follow-up and not auto-cancelled (edge case).

### listing_photos
`id, listing_id, storage_key, variants jsonb, position, alt_sw, alt_en`. 1–20 per listing,
and at least 1 is required to submit for review.

### listing_prices
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| listing_id | FK | |
| unit | enum `hour`,`night`,`day`,`week`,`month`,`item_day` | must be in the category's `price_units` |
| amount_tzs | bigint | `> 0` |
| season_start, season_end | date NULL | both or neither; seasons of the same unit must not overlap (exclusion constraint) |

Exactly one non-seasonal row per unit.

---

## Availability & booking

### availability_blocks
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| listing_id | FK | |
| period | tstzrange NOT NULL | half-open `[)`, non-empty |
| quantity | int | `>= 1`; 1 for exclusive modes |
| kind | enum `exclusive`,`stock` | from the category's booking mode |
| source | enum `booking`,`owner_block` | |
| booking_id | FK NULL | required when `source=booking` |
| active | bool | false when the booking is cancelled or expired |

Constraint (R1):
```sql
EXCLUDE USING gist (listing_id WITH =, period WITH &&)
  WHERE (kind = 'exclusive' AND active)
```
Stock check (QUANTITY): under `SELECT … FOR UPDATE` on the listing, for each day of the
request `stock - SUM(quantity of active overlapping blocks) >= requested`. An owner block in
QUANTITY mode reserves a quantity (e.g. 2 tents in repair).

### bookings
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| code | text UNIQUE | human readable, e.g. `EHG-7K3QX` |
| listing_id, renter_id, owner_profile_id | FK | renter ≠ listing owner's user (edge case) |
| booking_mode | enum | copied from category |
| period | tstzrange | |
| quantity | int | default 1 |
| status | enum `requested`,`awaiting_payment`,`confirmed`,`in_progress`,`completed`,`cancelled`,`disputed` | R17 |
| quote | jsonb | priced line items snapshot (R5) |
| rental_tzs, delivery_fee_tzs, service_fee_tzs, deposit_tzs, total_tzs | bigint | `total = rental + delivery + service + deposit` |
| commission_bps, commission_tzs | int, bigint | snapshotted from category |
| cancellation_policy | enum | snapshotted |
| delivery_requested | bool; delivery_address text NULL | |
| payment_due_at | timestamptz NULL | +15 min instant / +24 h after accept (FR-017) |
| request_expires_at | timestamptz NULL | +24 h for requests (FR-018) |
| lease_months | int NULL | LEASE only |
| cancelled_by | enum `renter`,`owner`,`admin`,`system` NULL | |
| cancel_reason | text NULL | |
| completed_at | timestamptz NULL | |

When a request is created, its exclusive or stock block is inserted immediately, so it holds
the dates while the owner decides. It is released on decline or expiry. Index
`(status, payment_due_at)` and `(status, request_expires_at)` for the sweeper.

### booking_events
`id, booking_id, from_status, to_status, actor_user_id NULL, actor_kind (user|system|provider),
note, created_at`. Append-only audit of the lifecycle (FR-019).

### lease_installments
`id, booking_id, seq (1..n), period tstzrange, amount_tzs, due_at, status (pending|paid|overdue|waived),
payment_id NULL, reminded_at`. Installment 1 = first month and is paid together with the
deposit on acceptance (US3-AS4). The others are billed by the worker 7 days before `due_at`,
with a reminder 2 days before (FR-020).

---

## Payments & money

### payments
| Field | Type | Rules |
|---|---|---|
| id | uuid PK | also our external reference to the provider |
| booking_id | FK | |
| lease_installment_id | FK NULL | |
| provider | text | `azampay` / `mock` |
| network | enum `mpesa`,`mixx`,`airtel`,`halopesa`,`azampesa` | |
| msisdn | text | paying number (may differ from login phone, edge case) |
| amount_tzs | bigint | |
| status | enum `pending`,`succeeded`,`failed`,`expired` | only `pending → *`, guarded update |
| provider_txn_id | text NULL UNIQUE (provider scoped) | |
| failure_reason | text NULL | |
| confirmed_at | timestamptz NULL | |

At most one `pending` payment per booking (partial unique index). The renter can retry on
another network after a failure.

### payment_events
`id, provider, provider_event_id, payment_id NULL, payload jsonb, received_at, processed_at`.
`UNIQUE(provider, provider_event_id)` makes callbacks idempotent (Principle III).

### refunds
`id, booking_id, payment_id, amount_tzs, reason enum(cancellation, deposit_return, owner_cancel,
admin, late_payment), status (pending|sent|failed), provider_ref, created_by`.

### claims
`id, booking_id, opened_by, kind (damage|dispute), description, evidence jsonb (storage keys),
amount_claimed_tzs NULL, status (open|resolved), resolution (owner_awarded|renter_refunded|split),
amount_awarded_tzs, resolved_by, resolved_at`. A damage claim must be opened ≤ 48 h after the
booking ends (FR-027), and an open claim blocks deposit auto-refund and payout of that booking.

### ledger_entries (append-only, R8)
| Field | Type | Rules |
|---|---|---|
| id | bigserial PK | |
| txn_id | uuid | groups the balanced rows of one money event |
| account | text | `provider_cash`, `renter_clearing`, `deposit_held`, `platform_revenue`, `owner_payable:<owner_id>` |
| amount_tzs | bigint | signed; per `txn_id` sum = 0 (deferred constraint trigger) |
| entry_type | enum `payment`,`commission`,`deposit_hold`,`deposit_release`,`refund`,`payout`,`adjustment` | |
| booking_id, payment_id, refund_id, payout_id | FK NULL | traceability (FR-025) |
| created_at | | |

A trigger forbids UPDATE and DELETE. Example, a confirmed booking with rental 200,000,
deposit 50,000 and 10% commission:
`provider_cash +250,000 · deposit_held −50,000 · platform_revenue −20,000 · owner_payable −180,000`
(sign convention: debit +, credit −). The owner's earnings view is
`−SUM(amount) WHERE account = 'owner_payable:<id>'`, split by booking (US4-AS1).

### payouts / payout_items
`payouts: id, owner_profile_id, payout_method snapshot jsonb, amount_tzs, status
(pending|processing|paid|failed), provider_ref, paid_at, failure_reason`.
`payout_items: payout_id, booking_id, amount_tzs` (UNIQUE booking_id, so a booking is paid out once).

---

## Trust & communication

### conversations / messages
`conversations: id, listing_id, renter_id, owner_profile_id, booking_id NULL, last_message_at`;
UNIQUE `(listing_id, renter_id)`.
`messages: id, conversation_id, sender_id, body (≤ 2000), body_masked bool, read_at`. Phone
numbers in the body are masked unless the conversation has a confirmed booking (R18).

### reviews
`id, booking_id, author_id, subject (listing|renter), rating 1–5, body ≤ 1000, created_at`.
UNIQUE `(booking_id, author_id)`. Allowed only when the booking is `completed` and the
author is its renter or owner (FR-029, US6-AS2). Listing, owner and renter averages are
recomputed on insert.

### abuse_reports
`id, reporter_id, target_kind (listing|user), target_id, reason, status (open|actioned|dismissed), handled_by`.

### notifications
`id, user_id, event (e.g. booking.confirmed), channel (sms|in_app), locale, payload jsonb,
status (queued|sent|failed), sent_at, provider_ref`. Templates are keyed by `event` in
`app/i18n/{sw,en}.json`.

---

## Platform

### jobs (worker queue, R9)
`id bigserial, kind, payload jsonb, run_at, attempts, max_attempts, locked_at, locked_by,
last_error, done_at, dedupe_key UNIQUE NULL`. Workers claim with
`FOR UPDATE SKIP LOCKED` and use exponential backoff.

### admin_audit_log
`id, admin_id, action, target_kind, target_id, before jsonb, after jsonb, created_at` for every
admin mutation (verification, approval, category edit, commission change, claim decision, refund).

---

## Key indexes (search, SC-002)
- `listings (status, category_id, district_id)` partial `WHERE status='active'`
- `listings USING gin (attributes jsonb_path_ops)`
- `listings (base_price_tzs)`, `listings (lat, lng)`, `listings USING gin (search_tsv)`
- `categories (path text_pattern_ops)`
- `availability_blocks USING gist (listing_id, period) WHERE active`
- `bookings (renter_id, created_at)`, `bookings (owner_profile_id, status)`
- `ledger_entries (account)`, `ledger_entries (booking_id)`
