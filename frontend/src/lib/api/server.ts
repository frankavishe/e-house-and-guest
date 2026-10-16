// Server-side API client for server components and route handlers. Calls FastAPI directly
// (API_INTERNAL_URL) and forwards the visitor's cookies and language.
import { cookies } from "next/headers";
import { getLocale } from "next-intl/server";
import createClient from "openapi-fetch";
import type { paths } from "./schema";

const baseUrl = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function serverApi() {
  const [jar, locale] = await Promise.all([cookies(), getLocale()]);
  const cookie = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  return createClient<paths>({
    baseUrl,
    headers: { "Accept-Language": locale, ...(cookie ? { Cookie: cookie } : {}) },
    cache: "no-store",
  });
}

/** The signed-in user, or null (expired access token counts as signed out here). */
export async function getCurrentUser() {
  const api = await serverApi();
  try {
    const { data } = await api.GET("/api/v1/me");
    return data ?? null;
  } catch {
    return null; // API unreachable: render the page signed out rather than failing
  }
}
