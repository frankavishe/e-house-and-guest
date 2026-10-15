# Feature Specification: Rental Marketplace MVP

**Feature Branch**: `001-rental-marketplace-mvp`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "This project is about renting rooms, business offices, vehicles,
office supplies, events & party supplies (tents, tables, chairs, lighting rigs, audio-visual
gear, bounce houses), vehicles & mobility, event halls, guest houses, student housing rentals,
serviced apartments, self-storage facilities, co-living spaces, office space rentals,
coworking spaces, event venue rentals, warehouse rentals, parking space rentals, construction
equipment rentals, party and event equipment rentals, IT and audiovisual equipment rentals.
The market is Tanzania; it is all about renting."

## Overview

A multi-vendor marketplace where owners in Tanzania list anything rentable, and renters find,
book and pay for it with mobile money. All rental types share one flow, grouped into six
categories, each with a booking style that fits how the item is rented:

| Category | Includes | How it is booked |
|---|---|---|
| Accommodation | Rooms, guest houses, serviced apartments, student housing, co-living | By night (date range); by month for student housing and co-living |
| Workspace | Business offices, office space, coworking | By hour/day (coworking); by month (offices) |
| Venues | Event halls, event venues | By hour or day |
| Storage & Property | Warehouses, self-storage, parking | By month; by day for parking |
| Vehicles & Mobility | Cars, vans, buses, motorbikes, bajaji, trucks | By day (date range), optional driver |
| Equipment & Supplies | Construction, party & event (tents, tables, chairs, lighting, AV, bounce houses), IT & AV, office supplies | Quantity × days |

The four booking styles are: **date range**, **time slot**, **lease** (monthly, owner approves
the request first) and **quantity** (number of units over a date range, limited by stock).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find something to rent (Priority: P1)

A renter opens the site on a phone, picks a category (e.g. "Guest houses" or "Tents"), chooses
a region/district and dates, filters by category-specific details (bedrooms, seating capacity,
vehicle type, tonnage…) and price, and opens a listing to see photos, price, location,
availability and reviews. Everything is in Swahili by default, with a switch to English.

**Why this priority**: Without discoverable listings there is no marketplace; this is also the
first thing visitors judge the product on.

**Independent Test**: With seeded listings in several categories, a visitor without an
account can find a matching listing in a chosen region and dates and see its full details.

**Acceptance Scenarios**:

1. **Given** active listings in Dar es Salaam and Arusha, **When** a visitor searches
   "Accommodation → Guest houses" in Arusha for 2 nights, **Then** only available Arusha guest
   houses are shown, each with the total price for the stay in TZS.
2. **Given** the "Vehicles" category, **When** the visitor filters by "4x4" and "with driver",
   **Then** only listings with those attributes are shown.
3. **Given** a listing is fully booked for the chosen dates, **When** the visitor searches
   those dates, **Then** that listing is not shown as available.
4. **Given** the site is in Swahili, **When** the visitor switches to English, **Then** all
   interface text changes to English and the visitor stays on the same page.

---

### User Story 2 - Book and pay with mobile money (Priority: P1)

A renter signs in with their phone number and a one-time code, books a listing (dates, time
slot, or quantity depending on the category), sees a price breakdown (rental, delivery if
any, service fee, refundable deposit, total), chooses a mobile money network, approves the
payment prompt on their phone and receives a confirmation by SMS and on screen.

**Why this priority**: Booking and payment is how the platform earns money and how renters
get value; together with Story 1 it forms the minimum viable product.

**Independent Test**: Using a test payment mode, a renter books and pays for one listing of
each booking style and each booking appears as confirmed, while the owner's calendar or
stock is reduced accordingly.

**Acceptance Scenarios**:

1. **Given** an available guest house room, **When** a renter books 3 nights and approves
   the M-Pesa prompt, **Then** the booking is confirmed, the renter gets an SMS receipt and
   the nights are blocked for other renters.
2. **Given** a tent listing with 10 in stock and 7 already booked for a date, **When** a renter
   tries to book 5 tents for that date, **Then** the system refuses and shows that 3 are
   available.
3. **Given** two renters try to book the last available slot at the same moment, **When**
   both submit, **Then** exactly one booking succeeds and the other is told the slot is
   taken.
4. **Given** a renter does not approve the payment prompt within the payment window, **When**
   the window expires, **Then** the booking is released and the dates become available again.
5. **Given** a listing that requires owner approval (lease or non-instant listing), **When**
   the renter submits a request, **Then** no payment is taken until the owner accepts, after
   which the renter is asked to pay.

---

### User Story 3 - List an item and manage bookings as an owner (Priority: P2)

An individual or business owner registers, submits verification details (national ID or
business registration and tax number), and creates a listing through a step-by-step form
whose fields match the chosen category. They set prices (per hour/night/day/week/month or per
item per day), deposit, delivery option, instant-book or approval, and upload photos. They
then manage a calendar, accept or decline requests, and see upcoming bookings.

**Why this priority**: Supply is required for Story 1, but early supply can be seeded by the
team, so self-service listing comes right after the renter flow.

**Independent Test**: A new owner can register, create a listing in any category, get it
approved, see it in search, block dates on its calendar, and accept a booking request.

**Acceptance Scenarios**:

1. **Given** an owner creating a "Warehouse" listing, **When** they reach the details step,
   **Then** they see warehouse fields (floor area, ceiling height, loading bay…) and not
   vehicle or room fields.
2. **Given** a new listing is submitted, **When** an admin has not yet approved it, **Then**
   it does not appear in search.
3. **Given** an owner blocks 1–5 December on their calendar, **When** a renter searches those
   dates, **Then** the listing is not available.
4. **Given** a lease request for an office, **When** the owner accepts it, **Then** the renter
   is notified and asked to pay the first month plus deposit.

---

### User Story 4 - Owner earnings and payouts (Priority: P2)

After a booking completes, the platform keeps its commission and records the owner's net
earnings. Owners see earnings per booking and receive payouts to their mobile money number or
bank account.

**Why this priority**: Owners will only stay if they get paid reliably and transparently.

**Independent Test**: After a completed paid booking, the owner sees the gross amount,
commission and net amount, and a payout record is created for the net amount.

**Acceptance Scenarios**:

1. **Given** a completed booking of TZS 200,000 with a 10% commission, **When** the owner
   opens earnings, **Then** they see TZS 200,000 gross, TZS 20,000 commission and TZS 180,000
   payable.
2. **Given** a payout is sent, **When** it succeeds, **Then** it is marked paid with a
   reference and the owner gets an SMS.

---

### User Story 5 - Cancellations, deposits and refunds (Priority: P2)

Renters or owners can cancel bookings under the listing's cancellation policy. Refundable
deposits are returned after the rental ends unless the owner reports damage, which an admin
reviews.

**Why this priority**: Equipment, vehicles and venues carry damage risk; clear rules protect
both sides and reduce disputes.

**Independent Test**: Cancelling a paid booking under each policy produces the correct refund
amount, and a deposit is refunded automatically if no damage claim is raised in time.

**Acceptance Scenarios**:

1. **Given** a booking under a "flexible" policy cancelled more than 24 hours before start,
   **When** the renter cancels, **Then** they receive a full refund of the rental amount.
2. **Given** the owner cancels a confirmed booking, **When** the cancellation is saved,
   **Then** the renter receives a full refund and the owner's cancellation count increases.
3. **Given** a rental ended and the owner raised no damage claim within 48 hours, **When**
   that time passes, **Then** the deposit is refunded to the renter.

---

### User Story 6 - Reviews and messaging (Priority: P3)

Renters and owners exchange messages about a listing or booking, and after a completed
booking each side can leave a rating and review.

**Why this priority**: Builds trust and reduces off-platform deals, but bookings can work
without it at launch.

**Independent Test**: A renter can message an owner before booking, and after a completed
booking both can leave reviews that appear on the listing and profile.

**Acceptance Scenarios**:

1. **Given** a completed booking, **When** the renter leaves a 4-star review, **Then** it shows
   on the listing and updates its average rating.
2. **Given** no completed booking exists between two users, **When** one tries to review the
   other, **Then** it is not allowed.

---

### User Story 7 - Administer the marketplace (Priority: P3)

Admins verify owners, approve or suspend listings, manage categories and their fields
(including adding a new rental type), set commission rates, handle disputes and damage
claims, and view reports on bookings, revenue and payouts.

**Why this priority**: Needed for a safe launch, but early on a small team can do some of it
manually.

**Independent Test**: An admin can add a new sub-category with its own fields and it becomes
usable in listing creation and search without any other change.

**Acceptance Scenarios**:

1. **Given** an admin adds "Generators" under Equipment with fields "power (kVA)" and "fuel
   type", **When** an owner creates a listing, **Then** "Generators" and its fields are
   available, and renters can filter by them.
2. **Given** a pending owner verification, **When** the admin rejects it with a reason,
   **Then** the owner is notified with the reason and their listings stay unpublished.

---

### Edge Cases

- A renter's phone number is on a different network from the one chosen for payment.
- The payment provider confirms the payment twice, or confirms after the booking expired.
- An owner edits prices while a renter is in checkout (the renter pays the price shown when
  the booking was created).
- A booking spans a seasonal price change (each night/day is priced at its own rate).
- An equipment booking needs delivery outside the owner's delivery area.
- A listing is suspended while it has future confirmed bookings.
- Network loss during payment: the renter returns and sees the true payment status.
- Time slots crossing midnight, and bookings use East Africa Time (UTC+3).
- A renter books their own listing (not allowed).

## Requirements *(mandatory)*

### Functional Requirements

**Accounts & identity**

- **FR-001**: Users MUST be able to register and sign in with a Tanzanian phone number and a
  one-time SMS code; email is optional.
- **FR-002**: The system MUST support three roles: renter, owner and admin; one person may be
  both renter and owner.
- **FR-003**: Owners MUST provide verification details (individual: national ID; business:
  registration and tax numbers) and MUST be verified by an admin before their listings go
  live.
- **FR-004**: Users MUST be able to choose Swahili or English; Swahili is the default.

**Catalogue & listings**

- **FR-005**: The system MUST organise listings into the six categories and their
  sub-categories listed in the Overview, each linked to one booking style.
- **FR-006**: Each sub-category MUST define its own listing fields (e.g. bedrooms,
  capacity, vehicle type, floor area, stock quantity); admins MUST be able to add or change
  sub-categories and fields without a software release.
- **FR-007**: Owners MUST be able to create, edit, pause and delete listings with title and
  description (Swahili and/or English), photos, location (region, district, ward, optional
  map pin), prices, deposit, delivery option and fee, minimum/maximum rental duration,
  cancellation policy, and instant-book or approval-required.
- **FR-008**: Prices MUST be in TZS and support the units hour, night, day, week, month and
  per-item-per-day, with optional seasonal prices for date ranges.
- **FR-009**: New and materially edited listings MUST be approved by an admin before they
  appear in search.

**Search & discovery**

- **FR-010**: Visitors MUST be able to search without an account by category, location,
  dates/time, quantity, price range and the sub-category's own fields.
- **FR-011**: Search results MUST only include listings available for the requested period
  and quantity, and MUST show the total price for that request.
- **FR-012**: Results MUST be viewable as a list and on a map, and sortable by price, rating
  and newest.
- **FR-013**: Listing pages MUST be shareable as links (including via WhatsApp) and readable
  without signing in.

**Booking**

- **FR-014**: The system MUST support the four booking styles: date range, time slot, lease
  (owner approval then monthly payments) and quantity (limited by stock).
- **FR-015**: The system MUST never allow two bookings to use the same date, slot, lease
  period or more stock than exists.
- **FR-016**: Before payment the renter MUST see a breakdown: rental amount, delivery fee,
  service fee, refundable deposit and total.
- **FR-017**: Unpaid bookings MUST be released automatically after a payment window of 15
  minutes (instant book) or 24 hours after owner approval (request bookings).
- **FR-018**: Owners MUST be able to block dates/slots/stock manually and accept or decline
  booking requests; undecided requests expire after 24 hours.
- **FR-019**: Bookings MUST follow a clear lifecycle (requested, awaiting payment,
  confirmed, in progress, completed, cancelled, disputed) and both parties MUST be notified
  of each change by SMS and in the app.
- **FR-020**: For leases, the system MUST bill each month and remind the renter before each
  due date.

**Payments & money**

- **FR-021**: Renters MUST be able to pay with M-Pesa, Mixx by Yas (Tigo Pesa), Airtel Money
  and HaloPesa via a payment prompt on their phone.
- **FR-022**: A booking MUST become confirmed only after the payment is verified as
  successful; repeated payment notifications MUST NOT confirm or charge twice.
- **FR-023**: The platform MUST take a commission per booking, configurable per category
  (default 10% from the owner) plus an optional renter service fee (default 0%).
- **FR-024**: Owners MUST receive payouts of their net earnings to a mobile money number or
  bank account, with payout status visible to them.
- **FR-025**: Every payment, refund, deposit, commission and payout MUST be recorded and
  traceable to its booking; renters MUST receive a receipt.
- **FR-026**: Listings MUST use one of three cancellation policies (flexible, moderate,
  strict) that determine the refund amount; owner cancellations always refund the renter
  in full.
- **FR-027**: Deposits MUST be refunded automatically 48 hours after the rental ends unless
  the owner raises a damage claim, which an admin resolves.

**Trust & communication**

- **FR-028**: Renters and owners MUST be able to message each other in the app; phone
  numbers are shared only after a booking is confirmed.
- **FR-029**: After a completed booking, renter and owner MUST each be able to leave one
  rating (1–5) and review of the other / the listing.
- **FR-030**: Users MUST be able to report a listing or user; admins MUST be able to
  suspend them.

**Administration**

- **FR-031**: Admins MUST be able to manage owner verification, listing approval,
  categories and fields, commission rates, disputes and damage claims, and refunds.
- **FR-032**: Admins MUST have reports of bookings, gross booking value, commission earned,
  refunds and payouts by period, category and region.

**Privacy**

- **FR-033**: Users MUST be able to request deletion of their account and personal data,
  except records that must be kept for financial and legal reasons.

### Key Entities

- **User**: a person identified by phone number; name, optional email, language, roles.
- **Owner profile**: individual or business details, verification documents and status,
  payout destination.
- **Location**: region → district → ward hierarchy for Tanzania.
- **Category / sub-category**: name in Swahili and English, booking style, list of fields
  owners fill in and renters filter by, commission rate.
- **Listing**: something rentable owned by an owner, in one sub-category; its field values,
  location, photos, prices, stock (for equipment), deposit, delivery, policies, status.
- **Price**: an amount in TZS per unit (hour, night, day, week, month, item-day), optionally
  for a season.
- **Availability block**: a period (and quantity) that is unavailable, due to a booking or an
  owner block.
- **Booking**: a renter's reservation of a listing for a period (and quantity), with price
  breakdown and lifecycle status.
- **Payment / refund**: money received from or returned to a renter, with network and
  reference.
- **Payout**: money sent to an owner for one or more bookings, net of commission.
- **Damage claim / dispute**: an owner or renter complaint about a booking, resolved by admin.
- **Review**: rating and text tied to one completed booking.
- **Conversation / message**: messages between a renter and owner about a listing or
  booking.
- **Notification**: an SMS or in-app message sent to a user about an event.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time renter on a phone can find, book and pay for a listing in under 5
  minutes.
- **SC-002**: Search results appear in under 2 seconds for 95% of searches on a typical 3G
  connection.
- **SC-003**: Zero double bookings or overselling of stock in production and in load tests
  with concurrent attempts on the same item.
- **SC-004**: 100% of successful payments result in a confirmed booking, and no payment is
  ever charged or counted twice.
- **SC-005**: An owner can publish a first listing (submitted for approval) in under 10
  minutes.
- **SC-006**: Admins can add a new rental type and have it bookable the same day with no
  software release.
- **SC-007**: 100% of user-facing text is available in both Swahili and English.
- **SC-008**: Owner payouts are initiated within 48 hours of a booking being completed.
- **SC-009**: At least 80% of bookings started are paid and confirmed (checkout completion).

## Assumptions

- Launch market is mainland Tanzania and Zanzibar; currency is TZS only.
- Payments go through one licensed aggregator that supports all major mobile money networks;
  card payments are a later addition.
- Default commission is 10% charged to the owner; renter service fee is 0% at launch. Both
  are configurable per category.
- Cancellation policies — flexible: full refund until 24 h before start; moderate: full
  refund until 5 days before, 50% after; strict: 50% refund until 7 days before, none after.
- Delivery for equipment is arranged by the owner, who sets a fee and service area; the
  platform does not run logistics.
- Vehicle insurance and driver licensing are the owner's responsibility; the platform
  records the owner's declaration.
- The first release is a mobile-friendly website; native mobile apps are out of scope.
- Initial listings may be seeded by the team in Dar es Salaam, Arusha, Dodoma, Mwanza and
  Zanzibar.
