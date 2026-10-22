# Security review (T147)

Reviewed 2026-10-22 against the constitution's Security principle, research.md R10 (auth), R12
(storage) and R18 (PII), and the current code. Each area lists what is in place, what this review
changed and what remains.

## Sessions and cookies

| Cookie | Lifetime | Flags |
|---|---|---|
| `access_token` (JWT HS256) | 15 min | `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` when `COOKIE_SECURE=true` |
| `refresh_token` (random, stored hashed) | 30 days | same; `Path=/` so the web middleware can renew sessions on page loads |

- Refresh tokens rotate on every use. Replaying an old one revokes the whole token family
  (`test_refresh_reuse_revokes_family`).
- Access tokens are checked against the injectable clock and require the `sub`, `exp` and `typ`
  claims (`app/core/security.py`).
- OTPs are 6 digits, live 5 minutes, allow 5 attempts, and are stored as an HMAC keyed by
  `OTP_HMAC_KEY`. Each phone gets at most 3 codes per 15 minutes, and each IP 20 per hour.
- **Changed:** staging and prod now refuse to start with `COOKIE_SECURE=false` (see Secrets).

## CSRF

The browser only talks to the web origin. Next proxies `/api/*` to FastAPI, so the API has no
CORS configuration at all, and a cross-origin script can neither read responses nor pass a
preflight. Mutations are protected in layers:

1. **SameSite=Lax** cookies are not sent on cross-site POST, PUT, PATCH or DELETE requests in
   current browsers.
2. **JSON only.** Request bodies are Pydantic models. FastAPI (0.143) parses JSON only for JSON
   content types, and an HTML form cannot send one, so a forged form post fails validation.
3. **Header check (added in this review).** Every POST, PUT, PATCH or DELETE under `/api/v1` must
   carry `X-Requested-With`; otherwise the API returns `403 FORBIDDEN` (`require_api_request` in
   `app/core/deps.py`). This covers the 18 mutations that take no body, such as
   `POST /bookings/{id}/accept`, the admin approvals and `DELETE /me`, in older browsers that
   ignore SameSite, which are common on low-end Android phones. A cross-site form cannot set the
   header. The web client (`lib/api/client.ts`, `lib/api/server.ts`, `middleware.ts`) sends it.
   - Exempt: provider webhooks (`/webhooks/payments/{provider}/{secret}`), which are
     server-to-server and authenticated by the URL secret plus the provider's own check.
   - Test: `test_mutations_need_the_csrf_header`.
4. **GET is read-only, with one exception.** An AST check of every GET handler found one write:
   `GET /conversations/{id}/messages` marks the other party's messages read, because the thread
   polls it every 10 s. Lax cookies are sent on top-level cross-site GETs, so a forged link could
   flip read receipts, but only with the conversation's UUID. That is accepted for now. Moving
   the marking to a `POST …/read` would remove the exception.

Hosting rule: never serve untrusted content from a sibling subdomain of the web origin, because
same-site requests carry Lax cookies.

## Uploads and presigned URLs

| What | Bucket | TTL | Limits |
|---|---|---|---|
| Listing photo upload (PUT) | private `uploads/listings/{listing}/` | 10 min | JPEG/PNG/WebP, ≤ 15 MB, ≤ 20 per listing |
| Owner document upload (PUT) | private `owner-docs/{profile}/` | 10 min | JPEG/PNG/PDF, ≤ 10 MB |
| Claim evidence upload (PUT) | private `claims/{booking}/` | 10 min | JPEG/PNG/PDF, ≤ 10 MB, ≤ 10 per claim |
| Document and evidence links for admins (GET) | private | 5 min | admin only, audited |
| Listing photo variants | public | n/a | re-encoded WebP 320/640/1280 |

- Presigned PUTs sign the `Content-Type`.
- A key is accepted only under the caller's own prefix, so nobody can attach another owner's
  document or another booking's evidence.
- Photos are re-encoded after `exif_transpose`, which drops every EXIF tag including GPS. The
  original stays private.
- **Fixed in this review:** a presigned PUT cannot limit size, and the limits above were not
  checked anywhere. Photos were only checked for existence on confirm; documents and evidence
  were never checked. Now `app/integrations/uploads.py` checks every upload when it is confirmed
  or attached: it must exist and fit the limit (`FILE_TOO_LARGE`, 422), and an oversized object
  is deleted. This also keeps oversized images away from the image worker.

## PII in logs and at rest

- NIDA numbers, TINs and payout account numbers are encrypted with Fernet (`FERNET_KEY`) and only
  shown masked (`****0123`).
- The logging filter masks phone numbers (keeping the last 3 digits), NIDA numbers and TINs.
- **Fixed in this review:**
  - The filter sat only on the root handler. Uvicorn's loggers have their own handlers, so access
    logs carried full numbers from query strings (`GET /admin/users?q=0712…`). The filter is now
    also attached to `uvicorn`, `uvicorn.error` and `uvicorn.access`.
  - The filter now masks each argument in place instead of flattening the message, because
    uvicorn's access formatter unpacks the argument tuple.
  - Tracebacks (`exc_text`) are now masked too.
  - Test: `test_pii_filter_keeps_access_log_args_and_masks_tracebacks`.
- The console SMS provider prints full numbers and codes to stdout. It is dev-only, and prod
  refuses to start with it.

## Secrets and configuration

- All configuration comes from environment variables (`app/core/config.py`, pydantic-settings).
  No secret is committed except the public dev defaults.
- **Added in this review:** with `ENV=staging` or `ENV=prod` the API and worker refuse to start
  when any of these still has its dev default: `JWT_SECRET`, `OTP_HMAC_KEY`, `FERNET_KEY`,
  `PAYMENT_CALLBACK_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. They also refuse when
  `JWT_SECRET` is under 32 characters or `COOKIE_SECURE` is false.
- Prod additionally rejects `SMS_PROVIDER=console` and mock payment or payout providers. Test:
  `test_settings_refuse_dev_values_outside_dev`.
- The dev-only mock payment routes are mounted only when `ENV` is `dev` or `test`.

## Rate limits and client addresses

- Limits per window:
  - OTP: 3 per phone per 15 min, 20 per IP per hour
  - bookings: 10 per user per 10 min
  - messages: 30 per user per min
- Counters live in Postgres (`app/core/ratelimit.py`).
- **Found in this review:** browsers reach the API through the Next proxy, so `request.client`
  was always the web container. The "per IP" OTP limit was in fact 20 codes per hour for the
  whole site, and anyone could use it to lock everyone out of sign-in.
  - Uvicorn honours `X-Forwarded-For` only from addresses in `FORWARDED_ALLOW_IPS`.
  - Next passes an incoming `X-Forwarded-For` through but does not add one.
  - The dev compose now trusts the proxy (`--forwarded-allow-ips *`).
  - Production must run a load balancer or reverse proxy in front of Next that appends the
    client address, and set `FORWARDED_ALLOW_IPS` on the API to the web tier's addresses (see
    docs/operations.md).
  - Uvicorn uses the rightmost untrusted address, so a forged leading entry is ignored.

## Follow-ups

- **Unconfirmed uploads still occupy storage.** Someone with a presigned URL can PUT up to 5 GB
  within 10 minutes without ever confirming. Either switch to presigned POST policies with
  `content-length-range`, or add a bucket lifecycle rule that expires objects under
  `uploads/listings/` after a day (photo originals are kept only until processing).
- Set `PIL.Image.MAX_IMAGE_PIXELS` explicitly in the image job (Pillow's default allows about
  178 M pixels before refusing), and mark such photos as failed.
- Add security headers on the web app: `Content-Security-Policy`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`. Set HSTS at the TLS terminator.
- Admin accounts have phone OTP only; consider a second factor for admin sign-in.
- Run `pip-audit` / `npm audit` in CI.
