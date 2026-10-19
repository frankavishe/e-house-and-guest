// Server-side reads for the public pages (US1). `cache` dedupes calls made by a page and
// its `generateMetadata` within one request.
import { cache } from "react";
import type { Schemas } from "./client";
import { serverApi } from "./server";
import type { Pair } from "@/lib/search";

export type CategoryNode = Schemas["CategoryNode"];
export type CategoryDetail = Schemas["CategoryDetail"];
export type LocationOut = Schemas["LocationOut"];
export type ListingCard = Schemas["ListingCard"];
export type ListingDetail = Schemas["ListingDetail"];
export type Availability = Schemas["Availability"];
export type SearchPage = Schemas["Page_ListingCard_"];
export type ApiFailure = { status: number; code: string; message: string };

function failure(status: number, error: unknown): ApiFailure {
  const inner = (error as { error?: { code?: string; message?: string } } | undefined)?.error;
  return { status, code: inner?.code ?? "INTERNAL_ERROR", message: inner?.message ?? "" };
}

export const getCategories = cache(async (): Promise<CategoryNode[]> => {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/categories");
  return data ?? [];
});

export const getCategory = cache(async (slug: string): Promise<CategoryDetail | null> => {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/categories/{slug}", { params: { path: { slug } } });
  return data ?? null;
});

export const getLocations = cache(async (parentId?: number): Promise<LocationOut[]> => {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/locations", {
    params: { query: parentId ? { parent_id: parentId } : {} },
  });
  return data ?? [];
});

/** `GET /listings/search` with the page's pairs (including `attr.*`, which the typed
 * query cannot express, so the query string is serialised here). */
export async function searchListings(
  pairs: Pair[],
): Promise<{ page: SearchPage | null; error: ApiFailure | null }> {
  const api = await serverApi();
  const qs = new URLSearchParams(pairs).toString();
  const { data, error, response } = await api.GET("/api/v1/listings/search", {
    querySerializer: () => qs,
  });
  if (data) return { page: data, error: null };
  return { page: null, error: failure(response.status, error) };
}

export const getListing = cache(async (id: string): Promise<ListingDetail | null> => {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/listings/{listing_id}", {
    params: { path: { listing_id: id } },
  });
  return data ?? null;
});

export async function getAvailability(
  id: string,
  from: string,
  to: string,
): Promise<Availability | null> {
  const api = await serverApi();
  const { data } = await api.GET("/api/v1/listings/{listing_id}/availability", {
    params: { path: { listing_id: id }, query: { from, to } },
  });
  return data ?? null;
}

/** Leaf categories in tree order, labelled with their group (for category pickers). */
export function flattenCategories(
  nodes: CategoryNode[],
  label: (node: CategoryNode) => string,
): { value: string; label: string; leaf: boolean }[] {
  const out: { value: string; label: string; leaf: boolean }[] = [];
  const walk = (list: CategoryNode[], depth: number) => {
    for (const node of list) {
      out.push({
        value: node.slug,
        label: `${depth ? "  ".repeat(depth) + "· " : ""}${label(node)}`,
        leaf: Boolean(node.booking_mode),
      });
      walk(node.children ?? [], depth + 1);
    }
  };
  walk(nodes, 0);
  return out;
}
