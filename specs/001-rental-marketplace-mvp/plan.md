# Implementation Plan: Rental Marketplace MVP

**Branch**: `001-rental-marketplace-mvp` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-rental-marketplace-mvp/spec.md`

## Summary

A mobile-first, Swahili-first marketplace where Tanzanian owners list anything rentable and
renters search, book and pay with mobile money. Every rental type runs through **one
generic listing engine**: a category tree whose leaves define a booking mode (`DATE_RANGE`,
`TIME_SLOT`, `LEASE`, `QUANTITY`) and a JSON attribute schema that drives the owner form,
validation and search filters. A **Next.js** server-rendered frontend calls a **FastAPI**
modular monolith over a typed OpenAPI client. **PostgreSQL** guarantees no double booking
through an exclusion constraint (exclusive modes) and listing-row locks (stock mode). It
also stores an append-only double-entry money ledger. Payments use **AzamPay** MNO checkout
(M-Pesa, Mixx by Yas, Airtel Money, HaloPesa) behind a `PaymentProvider` interface, with
verify-by-status-query callbacks. A Postgres-backed worker handles expiries, deposits,
lease billing, payouts and SMS. Details: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5 on Node.js 20 LTS (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0 (async, asyncpg), Pydantic v2, Alembic,
httpx, Pillow, cryptography (Fernet), PyJWT; Next.js 15 (App Router), next-intl, Tailwind CSS,
openapi-typescript + openapi-fetch, Leaflet

**Storage**: PostgreSQL 16 (`btree_gist`, `pgcrypto`); S3-compatible object storage (MinIO
locally) for photos and private verification documents

**Testing**: pytest + pytest-asyncio + httpx against real Postgres; schemathesis contract
tests; Vitest; Playwright smoke tests (360×640); k6 for search load

**Target Platform**: Linux containers (api, worker, web) + managed Postgres; clients are
mobile browsers on 3G (Android Chrome first)

**Project Type**: Web application (frontend + backend)

**Performance Goals**: search API p95 < 500 ms server-side at 20k listings; search page
LCP < 2 s on slow 3G for 95% of loads (SC-002); payment confirmation visible ≤ 10 s after
provider callback

**Constraints**: ≤ 300 KB gz initial JS per route; TZS integer money; EAT business time;
no double booking under concurrency (SC-003); idempotent payment handling (SC-004);
sw + en for every string (SC-007); PDPA 2022

**Scale/Scope**: launch in 5 cities, ~5k listings, ~20k users, ≤ 50 bookings/min peak;
~40 screens (renter, owner, admin); 7 user stories, 33 FRs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Pre-research | Post-design |
|---|---|---|---|
| I. One generic listing engine | Category tree + 4 modes + JSONB attribute schema; no per-type tables or slug branches | ✅ | ✅ `categories.attribute_schema`, `listings.attributes`; night/day counting is category data (`default_unit`), not code; the seed table covers all 20 types with zero special tables |
| II. Tanzania-first | sw default/en; TZS integers; phone+OTP; regions→districts→wards; NIDA/TIN/BRELA | ✅ | ✅ R10, R13, R16; `*_tzs bigint`; `owner_profiles` fields; i18n parity tests |
| III. Mobile-money payments safely (v1.0.1) | `PaymentProvider` + mock; webhooks authenticated, confirmed through the provider status API, idempotent; confirm only on verified success; append-only ledger | ✅ | ✅ [contracts/providers.md](contracts/providers.md); `payment_events` unique key; status re-query; guarded updates; `ledger_entries` trigger forbids UPDATE/DELETE |
| IV. No double booking | Check + insert in one transaction with constraint/locks; concurrent tests per mode | ✅ | ✅ exclusion constraint on `availability_blocks`; `FOR UPDATE` on listing for stock; V6 concurrency suite |
| V. Test-first core logic | pytest first for availability, pricing, state machine, payments, authz; contract tests; UI smoke | ✅ | ✅ R15; quickstart gates |
| VI. Mobile-first low-bandwidth | SSR, optimised images, ≤ 300 KB JS, works without images | ✅ | ✅ server components by default; WebP variants + srcset; Leaflet lazy-loaded; bundle size check in CI |
| VII. Simplicity & boundaries | Backend owns rules; typed OpenAPI client; external services behind interfaces; modular monolith | ✅ | ✅ one API + one worker from the same codebase; no Redis/broker/search engine; one justified addition (below) |

**Result**: PASS. One item recorded in Complexity Tracking (worker process).

## Project Structure

### Documentation (this feature)

```text
specs/001-rental-marketplace-mvp/
├── plan.md              # this file
├── research.md          # Phase 0: decisions R1–R19
├── data-model.md        # Phase 1: tables, constraints, state machines
├── quickstart.md        # Phase 1: run + validation scenarios V1–V18
├── contracts/
│   ├── rest-api.md         # HTTP API contract
│   ├── attribute-schema.md # category field-definition format + seed categories
│   └── providers.md        # PaymentProvider / PayoutProvider / SmsProvider / StorageProvider
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
docker-compose.yml            # db, db-test, minio, api, worker, web
.env.example

backend/
├── pyproject.toml            # uv, ruff, mypy, pytest config
├── alembic/                  # migrations (only way to change schema)
├── seed/                     # locations.csv, categories.yaml, demo.yaml
├── app/
│   ├── main.py               # FastAPI app, routers, error handlers
│   ├── worker.py             # job runner + periodic sweeps (R9)
│   ├── core/                 # config, db session, security (JWT, OTP, Fernet), i18n, clock, errors
│   ├── i18n/                 # sw.json, en.json (SMS / notification / error texts)
│   ├── accounts/             # users, OTP auth, owner profiles, payout methods
│   ├── catalog/              # categories, attribute-schema validation, locations
│   ├── listings/             # listing CRUD, photos, prices, moderation states
│   ├── search/               # query builder (filters, availability, bbox, sort)
│   ├── availability/         # blocks, exclusion/stock checks, slot generation
│   ├── pricing/              # quote calculation (seasons, units, fees)
│   ├── bookings/             # state machine, create/accept/cancel, leases, claims
│   ├── payments/             # checkout, callbacks, reconciliation, refunds
│   ├── ledger/               # double-entry posting, balance views
│   ├── payouts/              # payout batching, disbursement
│   ├── messaging/            # conversations, messages, masking
│   ├── reviews/              # reviews, rating aggregates, abuse reports
│   ├── notifications/        # templates, outbox jobs, in-app feed
│   ├── admin/                # verification, moderation, categories, stats
│   ├── jobs/                 # jobs table, enqueue/claim helpers
│   └── integrations/         # payments/{azampay,mock}, sms/{beem,console}, storage/{s3,local}
└── tests/
    ├── unit/                 # pricing, state machine, schema validation, ledger
    ├── integration/          # API flows, concurrency, webhooks, sweeps
    └── contract/             # schemathesis + per-endpoint schema tests

frontend/
├── package.json              # next, next-intl, tailwind, openapi-fetch, leaflet, playwright, vitest
├── messages/                 # sw.json, en.json
├── src/
│   ├── app/[locale]/
│   │   ├── page.tsx                      # home: categories + search box
│   │   ├── search/                       # results list + map toggle, schema-driven filters
│   │   ├── l/[id]/                       # listing detail, availability, booking widget
│   │   ├── book/[bookingId]/             # checkout, payment status, receipt
│   │   ├── account/                      # sign-in (OTP), profile, my bookings, messages
│   │   ├── owner/                        # onboarding, listings wizard, calendar, requests, earnings
│   │   └── admin/                        # verifications, moderation, categories, claims, payouts, stats
│   ├── components/           # UI primitives, AttributeForm, AttributeFilters, Money, ImageWithFallback
│   ├── lib/api/              # generated schema.d.ts + client wrapper (server & client)
│   ├── lib/format.ts         # TZS, dates in EAT
│   └── middleware.ts         # locale routing, auth redirect
└── tests/
    ├── unit/                 # vitest (format, i18n parity)
    └── e2e/                  # playwright smoke: search → book → pay, owner listing, admin category
```

**Structure Decision**: A web application with two top-level apps, `backend/` (FastAPI
modular monolith plus a worker entry point sharing its code) and `frontend/` (Next.js).
Backend modules follow the domain areas in the spec. Each owns its models, schemas, service
and router, and cross-module calls go through service functions, not other modules' tables.
The Next.js app proxies `/api/*` to FastAPI (rewrite) so auth cookies are same-origin.

## Delivery order (input for /speckit-tasks)

1. **Foundation**: compose, config, DB, Alembic baseline, auth (OTP/JWT), i18n scaffolding,
   catalog + locations seed, typed client generation, CI gates.
2. **US1 Search** (P1): listings read model, schema-driven filters, availability-aware search,
   listing page, sw/en.
3. **US2 Book & pay** (P1): availability engine + concurrency tests, pricing, booking state
   machine, request accept/decline, lease billing, mock + AzamPay providers, webhooks,
   reconciliation, expiry sweeper, SMS + in-app notifications. *MVP cut.*
4. **US3 Owner listings** (P2): owner onboarding/verification, listing wizard, photos, prices,
   blocks, requests inbox UI, calendar, admin moderation (minimal).
5. **US4 Earnings & payouts** (P2): ledger views, payout batching, manual mark-paid.
6. **US5 Cancellations & deposits** (P2): policies, refunds, claims, deposit auto-release.
7. **US6 Reviews & messaging** (P3).
8. **US7 Admin** (P3): category/schema editor, reports, abuse handling, stats.

## Open items to verify (do not block tasks)

- AzamPay: official callback authentication, payload, sandbox credentials, disbursement
  support for wallets and banks (R6, R7).
- Beem: sender-ID registration lead time and cost (R11).
- Hosting region and PDPA cross-border transfer rules (R19).
- Location dataset licence (R16).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Separate `worker` process (same codebase, Postgres `jobs` table) | Time-based rules (15-min holds, 24 h request expiry, 48 h deposit release, lease billing, payouts, payment reconciliation) and SMS sending must run reliably outside request handling | Running a scheduler inside API processes duplicates jobs when several API workers run. Celery/Redis adds a broker to operate. Cron alone cannot retry with backoff or carry per-job state. |
