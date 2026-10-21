// Server-side reads for the owner and admin pages (US3). Each returns null when the API
// answers with an error (not an owner, not an admin, unknown id).
import type { Schemas } from "./client";
import { serverApi } from "./server";

export type OwnerProfile = Schemas["OwnerProfileOut"];
export type OwnerListing = Schemas["OwnerListingOut"];
export type OwnerListingPage = Schemas["Page_OwnerListingOut_"];
export type Calendar = Schemas["Calendar"];
export type VerificationPage = Schemas["Page_VerificationItem_"];
export type AdminListingPage = Schemas["Page_AdminListingItem_"];

export async function getOwnerProfile(): Promise<OwnerProfile | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/owner-profile");
  return data ?? null;
}

export async function getOwnerListings(page: number): Promise<OwnerListingPage | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/owner/listings", {
    params: { query: { page, page_size: 20 } },
  });
  return data ?? null;
}

export async function getOwnerListing(id: string): Promise<OwnerListing | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/owner/listings/{listing_id}", {
    params: { path: { listing_id: id } },
  });
  return data ?? null;
}

export async function getOwnerCalendar(from: string, to: string): Promise<Calendar | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/owner/calendar", {
    params: { query: { from, to } },
  });
  return data ?? null;
}

export async function getVerificationQueue(page: number): Promise<VerificationPage | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/owner-verifications", {
    params: { query: { status: "pending", page } },
  });
  return data ?? null;
}

export async function getListingQueue(page: number): Promise<AdminListingPage | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/admin/listings", { params: { query: { page } } });
  return data ?? null;
}
