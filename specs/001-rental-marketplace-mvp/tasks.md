---

description: "Task list for the Rental Marketplace MVP"
---

# Tasks: Rental Marketplace MVP

**Input**: Design documents from `specs/001-rental-marketplace-mvp/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (rest-api.md,
attribute-schema.md, providers.md), quickstart.md

**Tests**: REQUIRED. Constitution Principle V requires test-first work for availability,
pricing, the booking state machine, payments/webhooks, the ledger and authorization. It also
requires contract tests for every endpoint and UI smoke tests. Principle IV requires a
concurrency test per booking mode. Write each test task first and confirm it FAILS before
its implementation task.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested
on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1…US7)

## Path & code conventions

- Backend: `backend/app/<module>/` with `models.py` (SQLAlchemy), `schemas.py` (Pydantic),
  `service.py` (business rules, the only place other modules call), `router.py` (FastAPI).
  Tests in `backend/tests/{unit,integration,contract}/`.
- Frontend: `frontend/src/app/[locale]/…` (server components by default), shared UI in
  `frontend/src/components/`, every visible string in `frontend/messages/{sw,en}.json`.
- Money is `int` TZS (`*_tzs`), percentages are basis points (`*_bps`), instants are UTC
  `timestamptz` with business rules in `Africa/Dar_es_Salaam`. Time comes from the injectable
  clock in `backend/app/core/clock.py` so tests can freeze it.
- Every new user-facing text (UI, SMS, error message) is added to both `sw` and `en`
  catalogs in the same task.
- Schema changes are made only through Alembic migrations in `backend/alembic/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository skeleton, tooling and local environment

- [X] T001 Create the top-level layout from plan.md (`backend/`, `frontend/`, `docker-compose.yml`, `.env.example`, `.gitignore`, `.editorconfig`) and a root `README.md` linking to `specs/001-rental-marketplace-mvp/quickstart.md`
- [X] T002 Initialize the backend with uv in `backend/pyproject.toml` (Python 3.12; fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, pyjwt, cryptography, httpx, pillow, pyyaml; dev: pytest, pytest-asyncio, schemathesis, ruff, mypy, freezegun) with ruff/mypy(strict on `app/`)/pytest config sections
- [X] T003 [P] Initialize the frontend in `frontend/` with Next.js 15 App Router + TypeScript + Tailwind CSS; add next-intl, openapi-fetch, openapi-typescript, leaflet, react-leaflet, vitest, @playwright/test, @next/bundle-analyzer; scripts `dev`, `build`, `test`, `e2e`, `gen:api`, `size`, `lint` in `frontend/package.json`
- [X] T004 Write `docker-compose.yml` with services `db` (postgres:16), `db-test` (postgres:16, tmpfs), `minio` + bucket bootstrap (`public`, `private`), `api` (uvicorn, port 8000), `worker` (`python -m app.worker`), `web` (next dev, port 3000), and `backend/Dockerfile`, `frontend/Dockerfile`
- [X] T005 [P] Write `.env.example` with every setting from research.md (DATABASE_URL, TEST_DATABASE_URL, JWT_SECRET, OTP_HMAC_KEY, FERNET_KEY, PAYMENT_PROVIDER=mock, AZAMPAY_*, PAYMENT_CALLBACK_SECRET, SMS_PROVIDER=console, BEEM_*, STORAGE_PROVIDER=s3, S3_*, NEXT_PUBLIC_TILE_URL, ENV=dev)
- [X] T006 [P] Add CI workflow `.github/workflows/ci.yml`: backend ruff + mypy + pytest (with Postgres service) + `alembic upgrade head` on an empty DB; frontend lint + tsc + vitest + build + size budget + `gen:api --check`; Playwright smoke against compose

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Backend core

- [X] T007 Implement settings in `backend/app/core/config.py` (pydantic-settings, reads `.env`, provider selectors)
- [X] T008 [P] Implement the injectable clock in `backend/app/core/clock.py` (`now()` UTC, `EAT` zone helpers, `to_eat_midnight(date)`, freezable in tests)
- [X] T009 [P] Implement the error model in `backend/app/core/errors.py` (`AppError(code, status, details)`, handlers producing `{"error": {code, message, details}}` with a localized message, mapping for 401/403/404/409/422/429) per contracts/rest-api.md
- [X] T010 [P] Implement backend i18n in `backend/app/core/i18n.py` + `backend/app/i18n/sw.json` + `backend/app/i18n/en.json` (`t(key, locale, **params)`, `Accept-Language` dependency, default `sw`)
- [X] T011 [P] Implement PII-masking log filter in `backend/app/core/logging.py` (masks `+255…` phones, NIDA/TIN patterns)
- [X] T012 Implement async DB engine/session and `Base` (uuid7 ids, `created_at`/`updated_at` mixins) in `backend/app/core/db.py`
- [X] T013 Initialize Alembic in `backend/alembic/` (async env, naming convention) and baseline migration enabling `btree_gist` and `pgcrypto` in `backend/alembic/versions/0001_extensions.py`
- [X] T014 Create FastAPI app in `backend/app/main.py` (`/api/v1` prefix, error handlers, `GET /health` checking DB, OpenAPI at `/api/v1/openapi.json`, router registration)
- [X] T015 Create pytest fixtures in `backend/tests/conftest.py` (test DB migrated once per session, per-test transaction rollback, `client` httpx AsyncClient, frozen clock fixture, factory helpers for users/categories/listings, separate-connection helper for concurrency tests)

### Integrations (interfaces + local implementations)

- [X] T016 [P] Define provider protocols and DTOs in `backend/app/integrations/payments/base.py` (`PaymentProvider`, `PayoutProvider`, `Network`, `CheckoutStarted`, `PaymentStatus`, `CallbackEvent`, `RefundResult`, `PayoutResult`, `InvalidCallback`, `ProviderUnavailable`) per contracts/providers.md
- [X] T017 [P] Define `SmsProvider` in `backend/app/integrations/sms/base.py` and implement `ConsoleSmsProvider` (stdout in dev, in-memory outbox in test) in `backend/app/integrations/sms/console.py`
- [X] T018 [P] Define `StorageProvider` in `backend/app/integrations/storage/base.py` and implement S3/MinIO presign + put/get in `backend/app/integrations/storage/s3.py` and an in-memory/local version in `backend/app/integrations/storage/local.py`
- [X] T019 Implement provider selection/dependency injection in `backend/app/integrations/__init__.py` (env-driven factories, overridable in tests)

### Jobs & notifications backbone

- [X] T020 Create `jobs` model + migration in `backend/app/jobs/models.py` and `backend/alembic/versions/0002_jobs.py` (per data-model.md, `dedupe_key` unique)
- [X] T021 Implement `enqueue(kind, payload, run_at, dedupe_key)` and `claim_batch()` with `FOR UPDATE SKIP LOCKED`, retry with exponential backoff in `backend/app/jobs/service.py`
- [X] T022 Implement the worker loop and periodic-sweep registry (`@periodic(every=…)`, `@handler(kind)`) in `backend/app/worker.py`
- [X] T023 [P] Write unit tests for job claim/retry/dedupe in `backend/tests/integration/test_jobs.py`
- [X] T024 Create `notifications` model + migration and `notify(user_id, event, payload, channels)` that renders sw/en templates and enqueues `sms.send` jobs, plus the `sms.send` handler in `backend/app/notifications/{models,service,handlers}.py`

### Accounts & auth (FR-001, FR-002, FR-004)

- [X] T025 [P] Write auth tests first in `backend/tests/integration/test_auth.py`: OTP request/verify happy path, wrong code, 5-attempt limit, 5-minute expiry, 3-per-15-min rate limit (429), phone normalisation (`0712…` → `+255712…`), refresh rotation and reuse detection revokes family, logout
- [X] T026 [P] Write authorization tests first in `backend/tests/integration/test_authz.py`: public vs signed-in vs owner vs admin endpoints return 401/403 correctly; suspended user is rejected
- [X] T027 [P] Write contract tests for `/auth/*`, `/me` and `/health` in `backend/tests/contract/test_auth_contract.py`
- [X] T028 Create `users`, `otp_codes`, `refresh_tokens` models + migration in `backend/app/accounts/models.py` and `backend/alembic/versions/0003_accounts.py`
- [X] T029 Implement security helpers in `backend/app/core/security.py` (phone normalisation/validation, OTP generate + HMAC hash, JWT encode/decode, refresh token hashing, Fernet encrypt/decrypt, cookie setters)
- [X] T030 Implement auth service + router (`/auth/otp/request`, `/auth/otp/verify`, `/auth/refresh`, `/auth/logout`) in `backend/app/accounts/service.py` and `backend/app/accounts/router.py`
- [X] T031 Implement `current_user`, `require_owner`, `require_verified_owner`, `require_admin` dependencies in `backend/app/core/deps.py`
- [X] T032 Implement `GET/PATCH /me` in `backend/app/accounts/router.py` (language preference stored on user)

### Catalogue & locations (FR-005, FR-006)

- [X] T033 [P] Write attribute-schema validation tests first in `backend/tests/unit/test_attribute_schema.py`: schema validation (unique keys, sw+en labels, filter/type compatibility, min ≤ max) and listing value validation for every type in contracts/attribute-schema.md, including unknown keys → error
- [X] T034 Create `locations` and `categories` models + migration in `backend/app/catalog/models.py` and `backend/alembic/versions/0004_catalog.py`
- [X] T035 Implement attribute schema meta-validation and the dynamic Pydantic value-model builder (cached by `category_id` + `schema_version`) in `backend/app/catalog/attributes.py`
- [X] T036 Implement catalog service + public router (`GET /categories`, `GET /categories/{slug}`, `GET /locations`) in `backend/app/catalog/service.py` and `backend/app/catalog/router.py`
- [X] T037 [P] Build seed data `backend/seed/locations.csv` (31 regions, all districts, wards for Dar es Salaam, Arusha, Dodoma, Mwanza, Zanzibar Urban/West) and `backend/seed/categories.yaml` (6 groups + leaves, modes, units and attribute schemas per contracts/attribute-schema.md, all labels sw+en)
- [X] T038 Implement the idempotent seed command `python -m app.seed --locations --categories --demo --all` in `backend/app/seed.py`

### Listing core models (shared by US1–US3)

- [X] T039 Create `owner_profiles`, `payout_methods`, `listings`, `listing_photos`, `listing_prices` models + migration (enums, generated `search_tsv`, indexes from data-model.md) in `backend/app/accounts/models.py`, `backend/app/listings/models.py` and `backend/alembic/versions/0005_listings.py`
- [X] T040 Create `availability_blocks` and `bookings` models + migration with the exclusion constraint `EXCLUDE USING gist (listing_id WITH =, period WITH &&) WHERE (kind='exclusive' AND active)` in `backend/app/availability/models.py`, `backend/app/bookings/models.py` and `backend/alembic/versions/0006_bookings.py`
- [X] T041 Add demo data to `backend/seed/demo.yaml` (demo renter/owner/admin phones from quickstart.md, verified owner, ≥ 3 active listings per leaf category across the 5 cities with prices and photos placeholders, a tent listing with stock 10)

### Frontend foundation

- [X] T042 Configure next-intl locale routing (`/sw` default, `/en`) in `frontend/src/middleware.ts`, `frontend/src/i18n/request.ts`, `frontend/messages/sw.json`, `frontend/messages/en.json`, and the root layout with language switcher that keeps the current path in `frontend/src/app/[locale]/layout.tsx`
- [X] T043 [P] Configure `/api/*` → FastAPI rewrite and image domains in `frontend/next.config.ts`
- [X] T044 Generate the typed API client (`npm run gen:api` → `frontend/src/lib/api/schema.d.ts`) and wrappers that forward cookies on the server in `frontend/src/lib/api/client.ts` and `frontend/src/lib/api/server.ts`
- [X] T045 [P] Implement formatting helpers in `frontend/src/lib/format.ts` (TZS `TSh 1,250,000`, EAT dates/times, localized fields fallback) with tests in `frontend/tests/unit/format.test.ts`
- [X] T046 [P] Write i18n key-parity tests in `frontend/tests/unit/i18n-parity.test.ts` and `backend/tests/unit/test_i18n_parity.py` (SC-007)
- [X] T047 [P] Build UI primitives in `frontend/src/components/ui/` (Button, Input, Select, Sheet, Badge, Skeleton) and `ImageWithFallback` + `Money` in `frontend/src/components/` (layout must hold when images fail, Principle VI)
- [X] T048 Implement OTP sign-in pages (phone entry, code entry, name on first login) in `frontend/src/app/[locale]/account/sign-in/page.tsx` with a `returnTo` redirect
- [X] T049 Add the whole-schema schemathesis test in `backend/tests/contract/test_openapi_schemathesis.py` (every public endpoint in `/api/v1/openapi.json`, excluding `/webhooks` and `/dev`; runs against the seeded test DB; CI-blocking; picks up new endpoints automatically as stories add them)

**Checkpoint**: `docker compose up` runs. Migrations apply on an empty DB, seed loads, sign-in works with the console OTP, `/sw` and `/en` render, and CI is green.

---

## Phase 3: User Story 1 - Find something to rent (Priority: P1) 🎯 MVP

**Goal**: Visitors search by category, location, dates/quantity, price and category attributes, and see availability-aware results with totals plus full listing pages, in Swahili or English.

**Independent Test**: With seeded listings, a signed-out visitor finds an available listing in a chosen region and dates and opens its details (quickstart V1–V3).

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T050 [P] [US1] Pricing unit tests in `backend/tests/unit/test_pricing.py`: nights vs days counting, hourly slots, item × days, whole-week rate when cheaper, seasonal rate per night across a season boundary, delivery fee, renter service fee in bps with half-up rounding, deposit, integer-only totals
- [X] T051 [P] [US1] Availability query tests in `backend/tests/integration/test_availability_query.py`: exclusive overlaps (half-open ranges, check-out day free), owner blocks, stock remaining per day, inactive blocks ignored, time slots crossing midnight in EAT
- [X] T052 [P] [US1] Search integration tests in `backend/tests/integration/test_search.py` covering US1 acceptance scenarios 1–3: category subtree, region filter, `attr.*` exact/range/any_of filters, unknown attr → 422, unavailable listings excluded, `total_tzs` present when a period is given, sorting, bbox, pagination, only `active` listings of verified owners
- [X] T053 [P] [US1] Contract tests for `/categories`, `/locations`, `/listings/search`, `/listings/{id}`, `/listings/{id}/availability`, `/listings/{id}/quote` in `backend/tests/contract/test_catalog_search_contract.py`

### Implementation for User Story 1

- [X] T054 [P] [US1] Implement the pricing service `quote(listing, period_input, delivery)` → `Quote` (R5) in `backend/app/pricing/service.py` with schemas in `backend/app/pricing/schemas.py`
- [X] T055 [P] [US1] Implement period normalisation (PeriodInput per mode → `tstzrange` + quantity, R2) and duration limits in `backend/app/availability/periods.py`
- [X] T056 [US1] Implement availability reads (`is_available`, `available_quantity_by_day`, `unavailable_ranges`, `free_slots` from `slot_config`) in `backend/app/availability/service.py`
- [X] T057 [US1] Implement the search query builder (subtree via `path`, locations, `attr.*` parsed against the category schema, price range, `q` on `search_tsv`, NOT EXISTS availability / stock subquery, bbox, sort, pagination) in `backend/app/search/service.py`
- [X] T058 [US1] Implement `GET /listings/search`, `GET /listings/{id}` (no phone or exact address), `GET /listings/{id}/availability` and `POST /listings/{id}/quote` in `backend/app/search/router.py` and `backend/app/listings/router.py`
- [X] T059 [US1] Regenerate the API client and build the home page (category grid + search box, region and date pickers) in `frontend/src/app/[locale]/page.tsx`
- [X] T060 [P] [US1] Build `AttributeFilters` rendered from a category `attribute_schema` (exact/range/any_of widgets) in `frontend/src/components/AttributeFilters.tsx`
- [X] T061 [US1] Build the search results page (server-rendered list, ListingCard with total price, sort, filters sheet, pagination, URL-driven state) in `frontend/src/app/[locale]/search/page.tsx` and `frontend/src/components/ListingCard.tsx`
- [X] T062 [P] [US1] Build the lazy-loaded map view (Leaflet + OSM, bbox search on move, client-only dynamic import) in `frontend/src/components/SearchMap.tsx`
- [X] T063 [US1] Build the listing detail page (photo gallery with srcset, attributes with labels, prices, deposit, delivery, policy, owner badge, availability calendar/slots/stock, reviews placeholder, share link incl. WhatsApp, Open Graph meta) in `frontend/src/app/[locale]/l/[id]/page.tsx`
- [X] T064 [US1] Add all US1 strings to `frontend/messages/sw.json` and `frontend/messages/en.json`, and a Playwright smoke test (search → open listing → switch language keeps page, 360×640) in `frontend/tests/e2e/search.spec.ts`

**Checkpoint**: Quickstart V1–V3 pass (V3 with a seeded booking block). US1 is demo-able on its own.

---

## Phase 4: User Story 2 - Book and pay with mobile money (Priority: P1) 🎯 MVP

**Goal**: Signed-in renters book any of the four modes, see a price breakdown, pay with M-Pesa / Mixx / Airtel / HaloPesa, and get confirmation by SMS and on screen. Double booking is impossible and payments are idempotent.

**Independent Test**: With the mock provider, book and pay one listing per booking mode. Each becomes confirmed and the calendar or stock is reduced (quickstart V4–V9).

### Tests for User Story 2 ⚠️ (write first, must fail)

- [x] T065 [P] [US2] Booking state-machine unit tests in `backend/tests/unit/test_booking_state.py`: every allowed transition from research.md R17, every disallowed transition raises `INVALID_TRANSITION`, events recorded
- [x] T066 [P] [US2] Concurrency tests in `backend/tests/integration/test_concurrency.py`: 20 parallel create-booking attempts on the same DATE_RANGE nights, the same TIME_SLOT, the same LEASE start, and the last units of a QUANTITY listing; exactly the allowed number succeed, the others get `SLOT_TAKEN`/`INSUFFICIENT_STOCK` (SC-003, Principle IV)
- [x] T067 [P] [US2] Booking API integration tests in `backend/tests/integration/test_bookings.py` covering US2 acceptance scenarios 1–3 and 5: instant book → `awaiting_payment` with `payment_due_at` +15 min; request listing → `requested`, no payment allowed; stock refusal returns `available: 3`; own listing → `OWN_LISTING`; quote snapshot unaffected by a later owner price change; `Idempotency-Key` replay returns the same booking
- [x] T068 [P] [US2] Payment & webhook tests in `backend/tests/integration/test_payments.py`: mock success confirms the booking and writes balanced ledger rows; failure keeps it payable with another network; duplicate callback (`…0004`) confirms once, one SMS, one set of ledger rows; callback with a wrong secret → 404 and with bad auth → 401; success after expiry re-reserves if free, otherwise auto-refunds; reconciliation picks up a lost callback (`…0003`)
- [x] T069 [P] [US2] Ledger unit tests in `backend/tests/integration/test_ledger.py`: each posting sums to 0, UPDATE/DELETE rejected by trigger, owner balance derived correctly (Principle III)
- [x] T070 [P] [US2] Expiry sweeper tests in `backend/tests/integration/test_expiry.py` (frozen clock): unpaid instant booking cancelled after 15 min and block released (US2-AS4); accepted request unpaid after 24 h cancelled; status moves confirmed → in_progress → completed at period start/end
- [x] T071 [P] [US2] Contract tests for `/bookings*`, `/bookings/{id}/payments`, `/payments/{id}`, `/bookings/{id}/receipt` in `backend/tests/contract/test_bookings_contract.py`
- [x] T072 [P] [US2] Request handling tests in `backend/tests/integration/test_requests.py`: accept → `awaiting_payment` + 24 h `payment_due_at`; decline releases the hold; undecided request expires after 24 h (FR-018); lease accept asks for first month + deposit and schedules installments (US2-AS5, US3-AS4); only the listing owner may accept or decline
- [x] T073 [P] [US2] Write lease billing tests in `backend/tests/integration/test_leases.py` (frozen clock): installment billed 7 days before due, reminder 2 days before, overdue after 7 days notifies owner and admin (FR-020)

### Implementation for User Story 2

- [x] T074 [US2] Create `booking_events`, `lease_installments`, `payments`, `payment_events`, `refunds`, `ledger_entries` (+ balance-sum deferred trigger and no-update/delete trigger) and an idempotency-keys table in `backend/alembic/versions/0007_payments_ledger.py` with models in `backend/app/bookings/models.py`, `backend/app/payments/models.py`, `backend/app/ledger/models.py`
- [x] T075 [US2] Implement the ledger posting API (`post(txn_entries)`, `post_booking_payment`, `post_refund`, `post_deposit_release`, balance views) in `backend/app/ledger/service.py`
- [x] T076 [US2] Implement the booking state machine (transition table, guards, `booking_events` writes, notification hooks) in `backend/app/bookings/state.py`
- [x] T077 [US2] Implement reservation in `backend/app/availability/service.py`: `reserve_exclusive` (insert block, map exclusion violation → `SLOT_TAKEN`) and `reserve_stock` (`SELECT … FOR UPDATE` listing, per-day sum check → `INSUFFICIENT_STOCK{available}`), `release(booking)`
- [x] T078 [US2] Implement `create_booking` (one transaction: validate period, forbid own listing, quote snapshot incl. commission/policy, reserve, set status instant vs request, `payment_due_at`/`request_expires_at`, lease installments) in `backend/app/bookings/service.py`
- [x] T079 [US2] Implement booking endpoints `POST /bookings`, `GET /bookings`, `GET /bookings/{id}` (counterpart phone/address only when confirmed+, `can` flags), `GET /bookings/{id}/receipt` with `Idempotency-Key` support (`idempotency_keys` table, `IDEMPOTENCY_KEY_REUSED`) in `backend/app/bookings/router.py` and `backend/app/core/idempotency.py`
- [x] T080 [US2] Implement `accept`/`decline` (listing owner only) in `backend/app/bookings/service.py` with `POST /bookings/{id}/accept|decline` in `backend/app/bookings/router.py`, including the lease first-installment (first month + deposit) payment path
- [x] T081 [P] [US2] Implement `MockPaymentProvider` with the test-number behaviours from contracts/providers.md and dev-only `POST /dev/mock-payments/{id}/{succeed|fail}` in `backend/app/integrations/payments/mock.py` and `backend/app/payments/dev_router.py`
- [x] T082 [P] [US2] Implement `AzamPayProvider` (token auth, MNO checkout, status query, callback parse/authenticate, network mapping) in `backend/app/integrations/payments/azampay.py`; mark the callback-auth and status-endpoint details `TODO(verify R6)` until checked against the sandbox
- [x] T083 [US2] Implement the payment service: `start_payment` (one pending per booking), `handle_callback` (store event idempotently → status re-query → guarded `pending→succeeded` + booking confirm + ledger + notify in one transaction), late-success handling, `reconcile_pending` in `backend/app/payments/service.py`
- [x] T084 [US2] Implement payment endpoints `POST /bookings/{id}/payments`, `GET /payments/{id}` (forces status check if pending > 60 s), `POST /webhooks/payments/{provider}/{secret}` (excluded from the public client) in `backend/app/payments/router.py`
- [x] T085 [US2] Register worker jobs in `backend/app/bookings/jobs.py` and `backend/app/payments/jobs.py`: expire unpaid holds and stale requests, start/complete bookings, reconcile pending payments every minute, purge idempotency keys older than 24 h
- [x] T086 [US2] Implement lease installment billing, reminders and overdue handling as worker jobs in `backend/app/bookings/leases.py` (FR-020)
- [x] T087 [P] [US2] Implement the in-app notification feed endpoints `GET /notifications`, `POST /notifications/read` in `backend/app/notifications/router.py` (FR-019)
- [x] T088 [US2] Add SMS/in-app templates (booking requested, awaiting payment, confirmed + receipt, payment failed, expired) to `backend/app/i18n/sw.json` and `backend/app/i18n/en.json`
- [x] T089 [US2] Build the booking widget on the listing page (mode-specific inputs: date range, slot picker, months, quantity; live quote; delivery toggle; sign-in redirect) in `frontend/src/components/BookingWidget.tsx`
- [x] T090 [US2] Build checkout (price breakdown, network choice, paying number prefilled from login phone, start payment, 3 s status polling, retry on failure, expiry countdown) in `frontend/src/app/[locale]/book/[bookingId]/page.tsx`
- [x] T091 [US2] Build the receipt/confirmation page and "My bookings" list/detail in `frontend/src/app/[locale]/book/[bookingId]/receipt/page.tsx` and `frontend/src/app/[locale]/account/bookings/page.tsx`
- [x] T092 [US2] Build the notification bell + feed (unread count, mark read, link to booking) in `frontend/src/components/NotificationBell.tsx`, with sw/en strings
- [x] T093 [US2] Add US2 strings to `frontend/messages/{sw,en}.json` and a Playwright smoke test (search → book → pay with mock → confirmed, 360×640) in `frontend/tests/e2e/book-and-pay.spec.ts`

**Checkpoint**: Quickstart V4–V9 pass (V9 through the API: owner accepts via `POST /bookings/{id}/accept`). **MVP = Setup + Foundational + US1 + US2**, with listings seeded by the team.

---

## Phase 5: User Story 3 - List an item and manage bookings as an owner (Priority: P2)

**Goal**: Owners register and get verified, create schema-driven listings that go through admin approval, manage calendars and blocks, and accept or decline requests, including leases.

**Independent Test**: A new owner registers, creates a listing in any category, gets it approved, sees it in search, blocks dates and accepts a request (quickstart V9–V11).

### Tests for User Story 3 ⚠️ (write first, must fail)

- [x] T094 [P] [US3] Owner onboarding tests in `backend/tests/integration/test_owner_profile.py`: individual requires NIDA, business requires BRELA + TIN; numbers stored encrypted and never returned in full; `draft → pending → verified|rejected` with reason; resubmit after rejection
- [x] T095 [P] [US3] Owner listing tests in `backend/tests/integration/test_owner_listings.py` covering US3 acceptance scenarios 1–3: attributes validated against the category schema with per-field 422s; submit needs ≥1 photo and ≥1 price; pending listing absent from search; material edit on an active listing is stored in `pending_changes` (`review_state=pending`) while approved values stay live, admin approval applies it and rejection clears it; price-only edit applies immediately; seasonal price overlap rejected; owner block makes dates unavailable; delete refused with future confirmed bookings
- [x] T096 [P] [US3] Contract tests for `/owner-profile*`, `/owner/listings*`, `/owner/calendar`, `/bookings/{id}/accept|decline`, `/admin/owner-verifications*`, `/admin/listings*` in `backend/tests/contract/test_owner_contract.py`

### Implementation for User Story 3

- [x] T097 [US3] Implement the owner profile service + router (create/edit/submit, document presigned upload to the private bucket, payout methods CRUD with single default) in `backend/app/accounts/owner_service.py` and `backend/app/accounts/owner_router.py`
- [x] T098 [US3] Implement the listing management service (create draft, patch with schema validation, material-edit detection into `pending_changes`, prices replace with season-overlap check, `base_price_tzs` denormalisation, submit/pause/resume/delete rules) in `backend/app/listings/service.py`
- [x] T099 [US3] Implement photo upload flow (presign PUT, confirm, reorder, alt text, delete) and the `image.process` worker job (WebP 320/640/1280, strip EXIF/GPS) in `backend/app/listings/photos.py` and `backend/app/listings/jobs.py`
- [x] T100 [US3] Implement owner listing endpoints and owner blocks/calendar endpoints in `backend/app/listings/owner_router.py`
- [x] T101 [US3] Implement minimal admin moderation: verification queue approve/reject with reason + notification (US7-AS2) and listing review (new listings and `pending_changes`) approve/reject/suspend with diff, all writing `admin_audit_log`, in `backend/app/admin/moderation.py`, `backend/app/admin/router.py` and `backend/alembic/versions/0008_admin_audit.py`
- [x] T102 [US3] Add owner/moderation notification templates to `backend/app/i18n/{sw,en}.json`
- [x] T103 [US3] Build owner onboarding pages (become an owner, individual/business form, document upload, status) in `frontend/src/app/[locale]/owner/onboarding/page.tsx`
- [x] T104 [P] [US3] Build `AttributeForm` rendered from a category `attribute_schema` (all field types, groups, sw/en labels, client-side hints mirroring server rules) in `frontend/src/components/AttributeForm.tsx`
- [x] T105 [US3] Build the step-by-step listing wizard (category → details via AttributeForm → location pickers + map pin → photos uploader → prices/seasons/deposit/delivery → policies/instant book/slot config → review & submit) in `frontend/src/app/[locale]/owner/listings/[id]/edit/page.tsx` and `frontend/src/app/[locale]/owner/listings/page.tsx`
- [x] T106 [US3] Build the owner calendar (bookings + blocks, add/remove blocks incl. quantity) and requests inbox with accept/decline in `frontend/src/app/[locale]/owner/calendar/page.tsx` and `frontend/src/app/[locale]/owner/requests/page.tsx`
- [x] T107 [US3] Build the admin verification and listing review screens in `frontend/src/app/[locale]/admin/verifications/page.tsx` and `frontend/src/app/[locale]/admin/listings/page.tsx` (role-guarded admin layout in `frontend/src/app/[locale]/admin/layout.tsx`)
- [x] T108 [US3] Add US3 strings to `frontend/messages/{sw,en}.json` and a Playwright smoke test (owner creates a warehouse listing, admin approves, it appears in search) in `frontend/tests/e2e/owner-listing.spec.ts`

**Checkpoint**: Quickstart V10–V11 pass, and V9 works end-to-end through the owner requests inbox, with self-service supply.

---

## Phase 6: User Story 4 - Owner earnings and payouts (Priority: P2)

**Goal**: Completed bookings show gross, commission and net per booking, and payouts of net earnings reach the owner's mobile money or bank with visible status.

**Independent Test**: After a completed paid booking, the owner sees 200,000 / 20,000 / 180,000 and a payout record exists. Marking it paid sends an SMS (quickstart V12).

### Tests for User Story 4 ⚠️ (write first, must fail)

- [x] T109 [P] [US4] Earnings and payout tests in `backend/tests/integration/test_payouts.py` covering US4 acceptance scenarios 1–2: earnings totals and per-booking items from the ledger; the daily payout job groups eligible bookings (completed ≥ 24 h, no open claim) once (`payout_items.booking_id` unique); disburse success → `paid` with reference + SMS + ledger `payout` entry; failure → `failed` and retry; manual mark-paid; payout initiated within 48 h of completion (SC-008)
- [x] T110 [P] [US4] Contract tests for `/owner/earnings`, `/owner/payouts`, `/admin/payouts*` in `backend/tests/contract/test_payouts_contract.py`

### Implementation for User Story 4

- [x] T111 [US4] Create `payouts` and `payout_items` models + migration in `backend/app/payouts/models.py` and `backend/alembic/versions/0009_payouts.py`
- [x] T112 [P] [US4] Implement `MockPayoutProvider` in `backend/app/integrations/payments/mock.py` and `AzamPay` disbursement in `backend/app/integrations/payments/azampay.py` behind a feature flag (`AZAMPAY_DISBURSE_ENABLED`, default off until R7 is verified)
- [x] T113 [US4] Implement the payout service (eligibility query, batch creation, disburse, status polling, manual mark-paid, ledger posting, notifications) and the daily payout job in `backend/app/payouts/service.py` and `backend/app/payouts/jobs.py`
- [x] T114 [US4] Implement `GET /owner/earnings`, `GET /owner/payouts`, and admin `GET /admin/payouts`, `POST /admin/payouts/{id}/mark-paid|retry` in `backend/app/payouts/router.py`
- [x] T115 [US4] Build the owner earnings and payouts page and admin payouts screen in `frontend/src/app/[locale]/owner/earnings/page.tsx` and `frontend/src/app/[locale]/admin/payouts/page.tsx`, with sw/en strings

**Checkpoint**: Quickstart V12 passes.

---

## Phase 7: User Story 5 - Cancellations, deposits and refunds (Priority: P2)

**Goal**: Cancellations follow flexible/moderate/strict policies, owner cancellations refund in full, deposits auto-refund 48 h after the end unless a damage claim is raised, and admins resolve claims.

**Independent Test**: Cancelling under each policy yields the right refund, and a deposit auto-refunds when no claim is raised (quickstart V13–V14).

### Tests for User Story 5 ⚠️ (write first, must fail)

- [ ] T116 [P] [US5] Cancellation policy unit tests in `backend/tests/unit/test_cancellation_policy.py`: flexible (full until 24 h before start), moderate (full until 5 days, then 50%), strict (50% until 7 days, then none), boundaries in EAT, deposit always refunded on cancel, service fee handling
- [ ] T117 [P] [US5] Cancellation/refund/claim integration tests in `backend/tests/integration/test_cancellations.py` covering US5 acceptance scenarios 1–3: renter cancel refund amount; owner cancel full refund + `owner_cancellation_count` +1; blocks released; refund ledger entries; deposit auto-refund after 48 h with no claim; damage claim after 48 h rejected; open claim blocks deposit refund and payout; admin resolution (owner_awarded / renter_refunded / split) posts correct ledger entries
- [ ] T118 [P] [US5] Contract tests for `/bookings/{id}/cancel`, `/bookings/{id}/cancel-preview`, `/bookings/{id}/claims`, `/admin/claims*`, `/admin/bookings*` in `backend/tests/contract/test_cancellations_contract.py`

### Implementation for User Story 5

- [ ] T119 [US5] Create the `claims` model + migration in `backend/app/bookings/models.py` and `backend/alembic/versions/0010_claims.py`
- [ ] T120 [US5] Implement the cancellation policy calculator in `backend/app/bookings/policies.py`
- [ ] T121 [US5] Implement cancel (renter/owner/admin), cancel preview, refund creation via `PaymentProvider.refund` + refund job + ledger, and the deposit-release job (48 h after end, skipped if a claim is open) in `backend/app/bookings/service.py`, `backend/app/payments/refunds.py` and `backend/app/bookings/jobs.py`
- [ ] T122 [US5] Implement claims (open within 48 h, evidence upload keys, admin resolve with ledger postings, booking `disputed` transitions) in `backend/app/bookings/claims.py` and endpoints in `backend/app/bookings/router.py` and `backend/app/admin/router.py`
- [ ] T123 [US5] Add cancellation/refund/claim notification templates to `backend/app/i18n/{sw,en}.json`
- [ ] T124 [US5] Build cancel flow with refund preview and claim form on booking detail pages, and the admin claims screen, in `frontend/src/app/[locale]/account/bookings/[id]/page.tsx` and `frontend/src/app/[locale]/admin/claims/page.tsx`, with sw/en strings

**Checkpoint**: Quickstart V13–V14 pass.

---

## Phase 8: User Story 6 - Reviews and messaging (Priority: P3)

**Goal**: Renters and owners message each other in the app (phones masked before confirmation) and leave one review each after a completed booking.

**Independent Test**: A renter messages an owner before booking, and after completion both review and averages update (quickstart V15).

### Tests for User Story 6 ⚠️ (write first, must fail)

- [ ] T125 [P] [US6] Messaging tests in `backend/tests/integration/test_messaging.py`: renter starts/reuses a conversation, only participants can read, phone-like numbers masked until a confirmed booking exists, unread counts, polling with `after`
- [ ] T126 [P] [US6] Review and report tests in `backend/tests/integration/test_reviews.py` covering US6 acceptance scenarios 1–2: review only for completed bookings by a party, one per author per booking, averages update on listing/owner/renter; abuse report creation
- [ ] T127 [P] [US6] Contract tests for `/conversations*`, `/bookings/{id}/reviews`, `/listings/{id}/reviews`, `/users/{id}/reviews`, `/reports`, `/notifications*` in `backend/tests/contract/test_social_contract.py`

### Implementation for User Story 6

- [ ] T128 [US6] Create `conversations`, `messages`, `reviews`, `abuse_reports` models + migration in `backend/app/messaging/models.py`, `backend/app/reviews/models.py` and `backend/alembic/versions/0011_social.py`
- [ ] T129 [US6] Implement the messaging service + router with phone masking in `backend/app/messaging/service.py` and `backend/app/messaging/router.py`
- [ ] T130 [US6] Implement the reviews service + router (eligibility, rating aggregates) and abuse reports in `backend/app/reviews/service.py` and `backend/app/reviews/router.py`
- [ ] T131 [US6] Build inbox/conversation pages (10 s polling), "Message owner" on listing page, review form on completed bookings, reviews on listing and profile pages, and report button in `frontend/src/app/[locale]/account/messages/` and `frontend/src/components/`, with sw/en strings

**Checkpoint**: Quickstart V15 passes.

---

## Phase 9: User Story 7 - Administer the marketplace (Priority: P3)

**Goal**: Admins manage categories and their fields (new rental types without a release), commission rates, bookings, abuse and users, and see reports by period, category and region.

**Independent Test**: An admin adds "Generators" with power (kVA) and fuel type. It is immediately listable and filterable (quickstart V16).

### Tests for User Story 7 ⚠️ (write first, must fail)

- [ ] T132 [P] [US7] Category admin tests in `backend/tests/integration/test_admin_categories.py` covering US7 acceptance scenario 1: create leaf with schema → listable and filterable at once; schema edits bump `schema_version` and invalidate the cache; type change or option removal in use → 409; commission/fee changes apply to new bookings only
- [ ] T133 [P] [US7] Admin operations tests in `backend/tests/integration/test_admin_ops.py`: suspend/unsuspend users and listings (future bookings flagged, not cancelled), abuse report actioning, stats totals by month/category/region match the ledger, CSV export, every mutation writes `admin_audit_log`
- [ ] T134 [P] [US7] Contract tests for `/admin/categories*`, `/admin/users*`, `/admin/reports-abuse*`, `/admin/stats` in `backend/tests/contract/test_admin_contract.py`

### Implementation for User Story 7

- [ ] T135 [US7] Implement admin category management (create/edit with schema meta-validation, in-use checks, cache invalidation) in `backend/app/admin/categories.py`
- [ ] T136 [US7] Implement admin user/listing suspension, abuse report handling and booking admin actions in `backend/app/admin/moderation.py`
- [ ] T137 [US7] Implement stats/reports (bookings, GBV, commission, refunds, payouts grouped by month/category/region; CSV) in `backend/app/admin/stats.py` and endpoints in `backend/app/admin/router.py`
- [ ] T138 [US7] Build the admin category & field editor (sw/en labels, field types, options, filter type, preview of the owner form and filters) in `frontend/src/app/[locale]/admin/categories/page.tsx`
- [ ] T139 [US7] Build admin users/abuse/bookings screens and the stats dashboard with CSV download in `frontend/src/app/[locale]/admin/{users,reports,bookings,stats}/page.tsx`, with sw/en strings
- [ ] T140 [US7] Playwright smoke test: admin adds "Generators", owner lists one, renter filters by kVA in `frontend/tests/e2e/admin-category.spec.ts`

**Checkpoint**: Quickstart V16 passes. All user stories are functional.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T141 Implement account deletion (FR-033): `DELETE /me` schedules anonymisation job (name/phone/email tombstoned, documents and messages deleted, bookings/ledger kept) in `backend/app/accounts/deletion.py` with tests in `backend/tests/integration/test_account_deletion.py`
- [ ] T142 [P] Implement `BeemSmsProvider` in `backend/app/integrations/sms/beem.py` with tests against a stubbed HTTP server in `backend/tests/integration/test_beem.py`
- [ ] T143 [P] Delivery-area validation in quotes and bookings (`OUTSIDE_DELIVERY_AREA`) in `backend/app/pricing/service.py` with tests added to `backend/tests/unit/test_pricing.py`
- [ ] T144 [P] Add rate limiting for OTP, booking creation and messaging in `backend/app/core/ratelimit.py` (Postgres-backed counters)
- [ ] T145 [P] Search performance: k6 script `perf/search.js`, 20k-listing generator `backend/app/seed_perf.py`, check query plans and indexes until p95 < 500 ms (SC-002)
- [ ] T146 [P] Frontend performance pass: bundle budget ≤ 300 KB gz per route, image `sizes`, Lighthouse mobile slow-3G on home/search/listing (LCP < 2 s), recorded in `frontend/perf-report.md`
- [ ] T147 [P] Security review: cookie flags, CSRF posture for SameSite=Lax + JSON-only mutations, presigned URL TTLs, PII log masking check, secrets only from env, documented in `docs/security.md`
- [ ] T148 [P] Write operations docs (env vars, provider switch, AzamPay/Beem go-live checklist from research.md "Verify" items, backups) in `docs/operations.md`
- [ ] T149 Run the full quickstart.md validation (V1–V18) on a fresh `docker compose up` and record results in `specs/001-rental-marketplace-mvp/checklists/validation.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → user stories → **Polish (Phase 10)**
- Foundational blocks every story.

### User story dependencies

| Story | Depends on | Notes |
|---|---|---|
| US1 Search (P1) | Foundational | Uses seeded listings; independent |
| US2 Book & pay (P1) | Foundational, US1 (pricing T054, availability reads T056, listing page T063) | Completes the MVP |
| US3 Owner listings (P2) | Foundational; US2 (accept/decline endpoints used by the requests inbox) | Listing CRUD can start in parallel with US2 |
| US4 Earnings & payouts (P2) | US2 (ledger, completed bookings) | |
| US5 Cancellations & deposits (P2) | US2 (payments, ledger, state machine) | Parallel with US4 |
| US6 Reviews & messaging (P3) | Foundational; completed bookings from US2 for reviews | Messaging can start after Foundational |
| US7 Admin (P3) | Foundational, US3 moderation base (T101) | Category editor can start after Foundational |

### Within each story

Tests (fail first) → migrations/models → services → endpoints → regenerate client → UI → e2e smoke.

## Parallel Examples

```text
# US1 tests together
T050 test_pricing.py · T051 test_availability_query.py · T052 test_search.py · T053 contract tests
# US1 independent implementation
T054 pricing/service.py · T055 availability/periods.py · T060 AttributeFilters.tsx · T062 SearchMap.tsx

# US2 tests together
T065 state machine · T066 concurrency · T067 bookings API · T068 payments · T069 ledger · T070 expiry · T071 contracts · T072 requests · T073 leases
# US2 providers in parallel
T081 MockPaymentProvider · T082 AzamPayProvider

# After US2: US4 and US5 in parallel (different modules: payouts/ vs bookings/policies + claims)
```

## Implementation Strategy

### MVP first (P1 stories)

1. Phase 1 Setup → Phase 2 Foundational
2. Phase 3 US1 → validate V1–V3
3. Phase 4 US2 → validate V4–V9 → **STOP: demo the MVP** with team-seeded listings and the mock provider, then the AzamPay sandbox

### Incremental delivery

4. US3 (self-service supply) → 5. US4 + US5 (money trust) → 6. US6 + US7 → 7. Polish and go-live checklist

### Before production payments

The R6/R7 verification items (AzamPay callback authentication, status endpoint, disbursement)
must be closed and `TODO(verify R6)` removed from `azampay.py`.

## Notes

- `[P]` = different files, no unfinished dependencies. Same-file tasks are sequential.
- Commit after each task or logical group, and stop at any checkpoint to validate.
- Regenerate the frontend API client (`npm run gen:api`) after any backend endpoint change.
