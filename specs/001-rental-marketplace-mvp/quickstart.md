# Quickstart & Validation Guide: Rental Marketplace MVP

How to run the system locally and prove each user story works end-to-end. Endpoint details
are in [contracts/rest-api.md](contracts/rest-api.md). Entities are in [data-model.md](data-model.md).

## Prerequisites

- Docker Desktop (Compose v2)
- For running outside containers: Python 3.12 + `uv`, Node.js 20 LTS + npm
- Ports free: 3000 (web), 8000 (API), 5432 (Postgres), 9000/9001 (MinIO)

## Start

```powershell
Copy-Item .env.example .env          # defaults: PAYMENT_PROVIDER=mock, SMS_PROVIDER=console, STORAGE_PROVIDER=s3 (MinIO)
docker compose up --build            # db, minio, api, worker, web
docker compose exec api uv run alembic upgrade head
docker compose exec api uv run python -m app.seed --all   # locations, 6 categories + leaves, demo users/listings in 5 cities
```

Open http://localhost:3000 (redirects to `/sw`). API docs: http://localhost:8000/api/v1/docs.

Starter accounts (OTP codes appear in `docker compose logs api` via the console SMS provider):
admin Frank Kavishe `0774861380`, owner Francis Kavishe `0793403553` (verified). There are no
demo listings; `python -m app.seed --reset --demo` wipes users, listings and activity and
re-creates these two accounts.

## Automated checks (gates before merge)

```powershell
docker compose exec api uv run pytest                    # unit + integration + concurrency
docker compose exec api uv run pytest tests/contract     # schemathesis vs OpenAPI
docker compose exec api uv run ruff check . ; docker compose exec api uv run mypy app
docker compose exec web npm run gen:api -- --check       # OpenAPI client up to date
docker compose exec web npm run test                     # vitest incl. sw/en key parity
docker compose exec web npm run e2e                      # Playwright smoke @ 360x640
docker compose exec web npm run build ; docker compose exec web npm run size   # ≤ 300 KB gz JS per route
```

Migrations on an empty DB: `docker compose run --rm api uv run alembic upgrade head` against
a fresh volume must succeed.

## Validation scenarios

Use mock payment numbers from [contracts/providers.md](contracts/providers.md): `…0001`
succeeds, `…0002` fails, `…0003` never calls back, `…0004` calls back twice.

| # | Story | Steps | Expected |
|---|---|---|---|
| V1 | US1 search | Signed out, `/sw` → Malazi → Nyumba za wageni, region Arusha, 2 nights | Only available Arusha guest houses; each card shows total TZS for 2 nights; switching to EN keeps the page and filters |
| V2 | US1 filters | Vehicles, filter 4x4 + with driver | Only matching listings (`GET /listings/search?category=vehicles&attr.vehicle_type=4x4&attr.with_driver=true`) |
| V3 | US1 availability | Book a demo room for dates X (V4), then search X | That room is not listed |
| V4 | US2 date range | Renter books 3 nights, pays with M-Pesa `+255700000001` | `confirmed`, SMS in logs, nights blocked, ledger txn sums to 0 |
| V5 | US2 stock | Tent listing stock 10; book 7 for date D; then try 5 for D | 409 `INSUFFICIENT_STOCK` with `available: 3` |
| V6 | US2 concurrency | `pytest tests/integration/test_concurrency.py` | 20 parallel attempts per mode on the same slot or last units → exactly the allowed number succeed |
| V7 | US2 expiry | Instant book, pay with `…0003`, 16 min later (`pytest -k hold_expiry`, frozen clock) | Booking `cancelled` (system), dates free again |
| V8 | US2 idempotency | Pay with `…0004` | One confirmation, one set of ledger rows, one SMS |
| V9 | US2/US3 request | Book a lease office → owner accepts → renter pays first month + deposit | No payment possible before accept; after pay `confirmed`, installments 2..n scheduled |
| V10 | US3 owner | New phone → owner profile → admin verifies → create Warehouse listing | Form shows warehouse fields only; listing absent from search until admin approves |
| V11 | US3 blocks | Owner blocks 1–5 Dec | Listing unavailable for those dates in search |
| V12 | US4 earnings | Complete a TZS 200,000 booking (`pytest -k earnings` or run sweeper) | Earnings: 200,000 / 20,000 / 180,000; payout job creates payout; mark paid → SMS |
| V13 | US5 cancel | Flexible booking cancelled > 24 h before start | Full rental refunded; owner cancel → full refund + owner cancel count +1 |
| V14 | US5 deposit | Booking ended, no claim, advance 48 h | Deposit refund created, ledger `deposit_release` |
| V15 | US6 reviews | After completed booking, renter leaves 4★ | Listing average updates; review without completed booking → 403 |
| V16 | US7 new type | Admin adds "Generators" (schema from contracts/attribute-schema.md) | Owner can list a generator immediately; renters filter by kVA/fuel. No deploy. |
| V17 | i18n | `npm run test -- i18n` and backend `pytest -k i18n_parity` | sw and en key sets identical |
| V18 | Performance | `k6 run perf/search.js` against seeded 20k listings | p95 search API < 500 ms server-side; Lighthouse mobile (slow 3G) search page LCP < 2 s |
