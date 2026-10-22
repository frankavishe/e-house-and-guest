// Message namespaces sent to the browser. Server components read the whole catalogue on the
// server; client components only get what their part of the site uses, so the home and search
// pages don't carry ~30 KB of owner and admin strings in their HTML (Principle VI,
// frontend/perf-report.md). tests/unit/client-messages.test.ts checks that every client
// component's namespaces are covered here.

/** Header widgets and shared error messages, on every page. */
export const BASE_NAMESPACES = ["common", "nav", "notifications", "errors"] as const;

/** Extra namespaces per top-level route segment (`/[locale]/<section>/…`). */
export const SECTION_NAMESPACES = {
  l: ["booking", "period", "units", "messages", "report"],
  u: ["report"],
  book: [
    "booking",
    "period",
    "units",
    "cancel",
    "checkout",
    "claim",
    "networks",
    "paymentFailure",
    "refunds",
    "reviews",
  ],
  account: ["account", "messages", "signIn"],
  owner: [
    "owner",
    "ownerListings",
    "listingStatus",
    "wizard",
    "attributes",
    "filters",
    "map",
    "policy",
    "units",
    "calendar",
    "earnings",
    "networks",
    "requests",
  ],
  admin: [
    "admin",
    "adminCategories",
    "adminClaims",
    "adminPayouts",
    "adminReports",
    "adminUsers",
    "attributes",
    "claim",
    "report",
    "units",
  ],
} as const satisfies Record<string, readonly string[]>;

export type Section = keyof typeof SECTION_NAMESPACES;
