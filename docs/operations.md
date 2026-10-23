# Operations (T148)

How to configure, deploy, switch providers, go live and back up the rental marketplace. Security
decisions behind several of these settings are in [security.md](security.md). Design background is in
[research.md](../specs/001-rental-marketplace-mvp/research.md) (R-numbers below refer to it).

## Services

| Process | Command | Scale |
|---|---|---|
| `api` | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips <web tier> --workers N` | One process saturates at about 40 search requests/s (`perf/README.md`); size `--workers` or containers to traffic |
| `worker` | `uv run python -m app.worker` | One is enough. Jobs are claimed with `FOR UPDATE SKIP LOCKED`, so a second worker is safe for failover |
| `web` | Next.js production build (`npm run build` then `npm start`) | Stateless; proxies `/api/*` to `API_INTERNAL_URL` |
| Postgres 16 | managed | Holds everything, including jobs, rate limits and the ledger |
| S3-compatible storage | managed (S3, R2, …) | Two buckets: `public` (photo variants, anonymous read), `private` (originals, verification documents) |

The dev `docker-compose.yml` runs uvicorn with `--reload` and `--forwarded-allow-ips *`. Do not
copy either into production.

### Periodic sweeps (worker)

| Job | Every | What it does |
|---|---|---|
| `bookings.expire_holds` | 1 min | Cancels unpaid holds (15 min instant, 24 h after approval) and undecided requests |
| `bookings.advance` | 1 min | `confirmed → in_progress → completed` |
| `payments.reconcile` | 1 min | Re-queries `pending` payments older than 2 min (lost callbacks) |
| `payouts.poll` | 5 min | Checks the status of sent disbursements |
| `bookings.release_deposits` | 15 min | Refunds deposits 48 h after the end when no claim is open |
| `ratelimit.purge`, `idempotency.purge` | 1 h | Drop old counters and idempotency keys |
| `payouts.create` | 1 day | Groups each owner's available balance into one payout |

Every job is idempotent. If the worker is down, holds are not expired and payments are not
reconciled, so alert on it (for example, on the oldest `jobs` row with `done_at IS NULL` and
`run_at` more than a few minutes in the past).
Restart the worker after deploying new code; it does not reload.

### Deploy order

1. `uv run alembic upgrade head` (one-off container, before new code starts). Write migrations so
   the previous release keeps working against the new schema while the rollout runs.
2. Roll out `api` and `worker`.
3. Roll out `web`. Regenerate the client (`npm run gen:api`) in CI, never in production.

Seeds: `python -m app.seed --locations --categories` is safe on any database (it upserts).
**Never run `--demo` or `--all` in staging or prod**: it creates demo users with known phone
numbers, including an admin. `app.seed_perf` is for load tests only.

## Environment variables

All settings come from the environment (`backend/app/core/config.py`, template in `.env.example`).
"Prod" = must be set to a non-default value when `ENV=prod`.

| Variable | Default | Prod | Notes |
|---|---|---|---|
| `ENV` | `dev` | `prod` | `dev`/`test` mount the mock payment routes; `staging`/`prod` enable the startup guard below |
| `DB_PORT`, `DB_TEST_PORT`, `API_PORT`, `WEB_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT` | 5432 … 9001 | – | docker-compose host ports only |
| `DATABASE_URL` | local | yes | `postgresql+asyncpg://…`; use TLS (`?ssl=require`) to managed Postgres |
| `TEST_DATABASE_URL` | local | – | tests only |
| `JWT_SECRET` | dev value | yes, ≥ 32 chars | Rotating it signs everyone out of access tokens (refresh tokens survive) |
| `JWT_ACCESS_TTL_SECONDS` | 900 | – | |
| `JWT_REFRESH_TTL_SECONDS` | 2592000 | – | |
| `OTP_HMAC_KEY` | dev value | yes | Rotating it invalidates OTPs in flight only |
| `COOKIE_SECURE` | `false` | `true` | Required outside dev |
| `FERNET_KEY` | dev value | yes | Encrypts NIDA/TIN at rest. **Do not just replace it**: old rows become unreadable. Rotation needs a re-encryption script using `MultiFernet` |
| `PAYMENT_PROVIDER` | `mock` | `azampay` | |
| `PAYOUT_PROVIDER` | `manual` | `manual` or `azampay` | `azampay` falls back to manual while `AZAMPAY_DISBURSE_ENABLED=false` |
| `PAYMENT_CALLBACK_SECRET` | dev value | yes | Path segment of the callback URL; changing it means updating the URL in the AzamPay portal |
| `PUBLIC_API_BASE_URL` | `http://localhost:8000` | yes | Public HTTPS origin used to build callback URLs |
| `MOCK_CALLBACK_BASE_URL` | empty | – | dev only |
| `AZAMPAY_ENV` | `sandbox` | `live` | |
| `AZAMPAY_APP_NAME`, `AZAMPAY_CLIENT_ID`, `AZAMPAY_CLIENT_SECRET`, `AZAMPAY_API_KEY` | empty | yes | From the AzamPay merchant portal |
| `AZAMPAY_CALLBACK_PASSWORD` | empty | yes | See the go-live checklist (R6) |
| `AZAMPAY_DISBURSE_ENABLED` | `false` | after R7 is verified | |
| `AZAMPAY_DISBURSE_SOURCE_NAME`, `…_SOURCE_BANK`, `…_SOURCE_ACCOUNT` | empty | with disbursement | Platform account payouts are sent from |
| `SMS_PROVIDER` | `console` | `beem` | |
| `BEEM_API_KEY`, `BEEM_SECRET_KEY` | empty | yes | |
| `BEEM_SENDER_ID` | empty | yes | Must be registered with Beem and TCRA |
| `BEEM_BASE_URL` | `https://apisms.beem.africa` | – | |
| `STORAGE_PROVIDER` | `s3` | `s3` | `local` is for tests |
| `S3_ENDPOINT_URL` | MinIO | yes | Endpoint the API uses |
| `S3_PRESIGN_ENDPOINT_URL` | empty | if different | Browser-reachable endpoint written into presigned URLs |
| `S3_PUBLIC_BASE_URL` | MinIO | yes | Public URL of the `public` bucket (or its CDN) |
| `S3_REGION` | `us-east-1` | yes | |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `minioadmin` | yes | Scope the key to the two buckets |
| `S3_BUCKET_PUBLIC`, `S3_BUCKET_PRIVATE` | `public`, `private` | – | |
| `UPLOAD_MAX_BYTES` | 10485760 | – | |
| `BUSINESS_TIMEZONE` | `Africa/Dar_es_Salaam` | – | Day boundaries for nights, holds and payouts |
| `DEFAULT_LANGUAGE` | `sw` | – | |
| `API_INTERNAL_URL` | `http://localhost:8000` | yes | web → api, private network |
| `NEXT_PUBLIC_TILE_URL` | OSM tiles | review | OSM's public tile server forbids heavy use; switch to a paid or self-hosted tile source before launch |
| `FORWARDED_ALLOW_IPS` | uvicorn default (`127.0.0.1`) | yes | Read by uvicorn, not the app; see below |

**Startup guard** (`_refuse_dev_values_outside_dev`): with `ENV=staging` or `prod` the API and
worker refuse to start if any of `JWT_SECRET`, `OTP_HMAC_KEY`, `FERNET_KEY`,
`PAYMENT_CALLBACK_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` still has its dev default, if
`JWT_SECRET` is shorter than 32 characters, or if `COOKIE_SECURE` is false. With `ENV=prod` they
also refuse `SMS_PROVIDER=console` and a `mock` payment or payout provider.

Generating secrets:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET, OTP_HMAC_KEY, PAYMENT_CALLBACK_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FERNET_KEY
```

Keep them in the platform's secret store, one set per environment. Never reuse staging values in
prod.

## Reverse proxy and client addresses

Rate limits (`app/core/ratelimit.py`) key on the caller's IP, and browsers reach the API only
through the web tier. To keep "per IP" meaning per visitor:

1. Terminate TLS at a load balancer or reverse proxy in front of `web` that **appends** the client
   address to `X-Forwarded-For`. Set HSTS there.
2. Run uvicorn with `--proxy-headers` and `FORWARDED_ALLOW_IPS` (or `--forwarded-allow-ips`) set to
   the web tier's private addresses. Never `*` in production: anyone could then pick their own IP.
3. Keep the API off the public internet except for the payment callback path
   `/api/v1/webhooks/payments/…`, or expose that path through the same proxy.

## Switching providers

Every external service sits behind an interface chosen by an environment variable; the switch is
a config change plus a restart of `api` **and** `worker` (the worker sends SMS, reconciles payments
and sends payouts).

| Concern | Dev / test | Production | Variable |
|---|---|---|---|
| Payments | `mock` (numbers `…0001` succeed, `…0002` fail, `…0003` never call back, `…0004` call back twice) | `azampay` | `PAYMENT_PROVIDER` |
| Payouts | `manual` / `mock` | `manual`, later `azampay` | `PAYOUT_PROVIDER` + `AZAMPAY_DISBURSE_ENABLED` |
| SMS / OTP | `console` (codes in the API log) | `beem` | `SMS_PROVIDER` |
| Storage | MinIO (`s3`) | S3 / R2 (`s3`) | `S3_*` |

Order:

1. Staging with `AZAMPAY_ENV=sandbox`. Register the callback URL in the AzamPay portal:
   `{PUBLIC_API_BASE_URL}/api/v1/webhooks/payments/azampay/{PAYMENT_CALLBACK_SECRET}`.
2. Work through the go-live checklist on staging, including a real sandbox payment, a failed
   payment, a lost callback (reconcile picks it up) and a duplicate callback.
3. Prod with `AZAMPAY_ENV=live`, `PAYOUT_PROVIDER=manual`. Make one small real payment and refund.
4. Turn on disbursement only after R7 is verified.

Rollback: set the variable back and restart `api` and `worker`. Callbacks, `payments.reconcile`
and refunds all use the provider that is configured *now*, so a switch strands any payment still
`pending` with the old provider. Before switching, stop new checkouts (or wait for a quiet
period) until `SELECT count(*) FROM payments WHERE status = 'pending'` is 0.

## Go-live checklist

Items marked **Verify** in research.md and `TODO(verify …)` in the code. Each must be checked
against the real service and the code adjusted if it differs.

Payments, AzamPay (R6, `app/integrations/payments/azampay.py`)
- [ ] Checkout request and response schemas match the sandbox (`/azampay/mno/checkout`, all five networks).
- [ ] Callback payload fields used for `provider_event_id`, status and amount.
- [ ] How AzamPay authenticates callbacks. The code requires `AZAMPAY_CALLBACK_PASSWORD` in the
      `x-callback-password` header (`CALLBACK_PASSWORD_HEADER`); confirm the header name and scheme.
- [ ] Transaction status query: endpoint and response shape (used by callbacks and `payments.reconcile`).
- [ ] Refunds: whether they go out as disbursements, and the flow for each network.
- [ ] Callback source IPs, if AzamPay publishes them, allowed at the proxy.

Payouts, AzamPay disbursement (R7)
- [ ] Disbursement supports TZ mobile wallets **and** banks.
- [ ] Request/response shape and the disbursement status query (`payouts.poll`).
- [ ] Only then set `AZAMPAY_DISBURSE_ENABLED=true` and `PAYOUT_PROVIDER=azampay`. Until then
      payouts are sent by hand (see Routine operations); SC-008 (48 h) holds either way.

SMS, Beem (R11, `app/integrations/sms/beem.py`)
- [ ] Sender ID approved by Beem and TCRA. Apply early: this has a lead time of weeks.
- [ ] Payload and response codes (code 100 = submitted) confirmed against a live account.
- [ ] Per-SMS cost known and the account topped up; set a low-balance alert.
- [ ] Swahili and English templates (`app/i18n/{sw,en}.json`) registered if TCRA requires it.

Data and hosting
- [ ] R16: licence and currency of the NBS 2022 location dataset (`backend/seed/locations.csv`).
- [ ] R19: PDPA 2022 cross-border transfer rules checked before choosing the hosting region.
- [ ] Map tiles moved off the public OSM server (`NEXT_PUBLIC_TILE_URL`).

Security follow-ups from [security.md](security.md#follow-ups)
- [ ] Bucket lifecycle rule expiring unconfirmed uploads.
- [ ] Security headers on the web app; HSTS at the TLS terminator.
- [ ] `pip-audit` / `npm audit` in CI.

Final
- [ ] `ENV=prod` starts (the startup guard passes).
- [ ] Backups configured and one restore rehearsed (below).
- [ ] Worker liveness alert in place.

## Backups and restore

**Postgres** holds all business state, including the append-only ledger and the job queue.

- Use the managed service's point-in-time recovery, retained at least 14 days.
- Also take a daily logical dump kept off-site (another account or region), retained 90 days:
  ```sh
  pg_dump -Fc --no-owner "$DATABASE_URL_SYNC" > rental-$(date +%F).dump
  ```
  (`DATABASE_URL_SYNC` is the same URL without `+asyncpg`.) Dumps contain encrypted NIDA/TIN
  values; keep `FERNET_KEY` backed up separately, since a dump without the key cannot decrypt them.
- Restore the whole database, never single tables: ledger rows, bookings and payments must stay
  consistent, and the ledger's trigger rejects updates and deletes.

**Object storage**

- `private` bucket (photo originals, verification documents): enable versioning and replication.
  It cannot be rebuilt.
- `public` bucket (resized WebP variants): can be regenerated from the originals by re-running the
  image job, so versioning is optional.

**Restore drill** (do it once before launch, then each quarter):

1. Restore the latest dump into a fresh Postgres: `pg_restore --no-owner -d <new db> rental-YYYY-MM-DD.dump`.
2. Run `alembic upgrade head` (no-op if already current).
3. Point a staging `api` at it with the prod `FERNET_KEY` and check: sign in, a listing page, an
   owner's earnings page, and that `SELECT SUM(amount_tzs) FROM ledger_entries` is 0.
4. Record how long it took.

## Routine operations

- **Manual payouts.** `GET /admin/payouts` lists `pending` payouts oldest first. Send the money
  through the bank or mobile-money portal, then `POST /admin/payouts/{id}/mark-paid` with the
  provider reference. The owner gets an SMS.
- **A user is locked out by rate limits.** Limits are fixed windows (OTP: 3 per phone per 15 min).
  Wait it out, or delete their rows from `rate_limits` and `otp_codes` in an emergency.
- **Stuck payment.** `payments.reconcile` re-queries it every minute; a late success re-reserves
  the slot if still free, otherwise refunds automatically. Check `payment_events` for the raw callbacks.
- **Logs.** Phone numbers, NIDA numbers and TINs are masked by the logging filter
  (`app/core/logging.py`). Do not add logging that bypasses it.
- **Account deletion** (`DELETE /me`) runs as a job; bookings and ledger rows are kept
  anonymised for financial retention.
