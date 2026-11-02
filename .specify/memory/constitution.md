<!--
Sync Impact Report
- Version change: 1.0.0 → 1.0.1 (PATCH, clarification)
- Modified principles: III. Mobile-Money Payments Done Safely — webhook rule now reads
  "authenticated (signature where offered, otherwise shared secret) + confirmed through the
  provider's status API + idempotent" instead of "verify signatures", because the first
  aggregator (AzamPay) may not sign callbacks. Intent unchanged.
- Added sections: none
- Removed sections: none
- Templates requiring updates: none; specs/001-rental-marketplace-mvp/plan.md Constitution
  Check row III updated
- Follow-up TODOs: none
-->

# e house and guest Constitution

A multi-vendor rental marketplace for Tanzania: rooms, guest houses, student housing,
serviced apartments, co-living, offices and coworking, event halls and venues, warehouses,
self-storage, parking, vehicles, construction equipment, party and event equipment, IT and
audiovisual equipment, and office supplies. Owners list, renters search, book and pay; the
platform earns a commission.

## Core Principles

### I. One Generic Listing Engine

Every rentable thing MUST be modelled through the same listing engine: a category tree,
one of four booking modes (`DATE_RANGE`, `TIME_SLOT`, `LEASE`, `QUANTITY`) and a
category-defined attribute schema stored as data (JSONB). Adding a new rental type MUST be
possible by adding a category and its attribute schema, without new tables, endpoints or
pages. Per-rental-type tables or code branches on category slug are forbidden unless a spec
proves the generic engine cannot express the requirement.

Rationale: about 20 rental types share the same lifecycle; one engine keeps the code small
and lets the business add categories without engineering work.

### II. Tanzania-First

- Swahili is the default language and English is the second; every user-facing string,
  notification, SMS and email MUST exist in both before a feature ships.
- All money is Tanzanian Shillings (TZS), stored as integers (no floats), shown with
  thousands separators.
- Phone number (+255) is the primary identity; login MUST work with phone + OTP alone.
- Locations use Tanzania regions → districts → wards plus optional map coordinates.
- Owner verification supports Tanzanian documents (NIDA, TIN, BRELA).

Rationale: the market is Tanzania; the product must feel local, not translated.

### III. Mobile-Money Payments Done Safely (NON-NEGOTIABLE)

- Payments go through a `PaymentProvider` interface; the first provider is an aggregator
  covering M-Pesa, Mixx by Yas (Tigo Pesa), Airtel Money and HaloPesa. A mock provider MUST
  exist for development and tests.
- Payment webhooks MUST be authenticated (provider signature where offered, otherwise a
  shared secret) and MUST NOT change state until the result is confirmed through the
  provider's status API. Webhooks MUST be idempotent; a repeated callback MUST NOT change
  state twice.
- A booking becomes `confirmed` only after a verified successful payment (or an explicit
  owner-approved offline-payment flow defined in a spec).
- Every money movement (payment, refund, deposit, commission, payout) MUST be recorded as an
  auditable ledger row; balances are derived, never edited by hand.

Rationale: money errors destroy trust in a marketplace faster than any other defect.

### IV. No Double Booking

Availability checks and booking creation MUST happen in one database transaction with row
locking (or equivalent constraint) so concurrent requests cannot oversell a date, slot,
lease period or equipment quantity. Each booking mode MUST have automated tests, including
a concurrent-booking test.

Rationale: double bookings are the core failure mode of any rental product.

### V. Test-First for Core Logic

Availability, pricing, the booking state machine, payments/webhooks and authorization MUST
be developed test-first (pytest on the backend). Contract tests MUST cover every public API
endpoint's request/response schema. UI work MUST at least have smoke tests for critical
flows (search → book → pay).

Rationale: these modules carry business and money risk; tests are their specification.

### VI. Mobile-First, Low-Bandwidth Web

The frontend MUST be designed for a 360px-wide phone on a slow 3G connection first:
server-rendered pages, optimised images, minimal client JavaScript, and no page whose
initial load exceeds 300 KB of JavaScript (gzipped) without a justification in the plan.
Core flows MUST remain usable when images fail to load.

Rationale: most Tanzanian users browse on phones with paid data.

### VII. Simplicity and Clear Boundaries

- The FastAPI backend is the only owner of business rules and data; the Next.js frontend
  consumes it through a typed client generated from the backend OpenAPI schema.
- External services (payments, SMS, file storage, maps) sit behind interfaces with a local
  or mock implementation.
- Start with a modular monolith. New services, queues or infrastructure require a written
  justification in the plan's Complexity Tracking section.

Rationale: a small team must be able to run, test and change the whole system locally.

## Technology & Platform Constraints

- **Frontend**: Next.js (App Router, TypeScript), next-intl (`/sw` default, `/en`),
  Tailwind CSS, Leaflet + OpenStreetMap for maps.
- **Backend**: FastAPI (Python 3.12+), SQLAlchemy 2.0, Pydantic v2, Alembic migrations.
- **Database**: PostgreSQL 16+. Schema changes only through Alembic migrations.
- **Local dev**: `docker compose up` MUST start PostgreSQL, backend and frontend.
- **Security**: JWT access + refresh tokens, role-based access (renter, owner, admin),
  secrets only via environment variables, personal data (NIDA, phone) never logged.
- **Privacy**: personal data handling MUST respect Tanzania's Personal Data Protection Act
  2022 (purpose limitation, consent, right to deletion).

## Development Workflow & Quality Gates

- Work follows Spec Kit: `/speckit-specify` → (`/speckit-clarify`) → `/speckit-plan` →
  `/speckit-tasks` → (`/speckit-analyze`) → `/speckit-implement`.
- Each feature lives on its own branch and spec folder under `specs/`.
- Every plan MUST include a Constitution Check against Principles I–VII.
- A change merges only when: tests pass, migrations apply cleanly on an empty database,
  OpenAPI client is regenerated if the API changed, and both `sw` and `en` translations exist.

## Governance

This constitution overrides other practices and conventions in the repository. Amendments
are made by editing this file through `/speckit-constitution`, with a Sync Impact Report,
and a semantic version bump: MAJOR for removing or redefining a principle, MINOR for adding
a principle or section, PATCH for clarifications. Every plan and code review MUST check
compliance; any deviation MUST be recorded and justified in the plan's Complexity Tracking
section.

**Version**: 1.0.1 | **Ratified**: 2026-10-15 | **Last Amended**: 2026-10-16
