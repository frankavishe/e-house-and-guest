// Browser API client. Requests go to this origin (`/api/*` is proxied to FastAPI), so the
// httpOnly auth cookies travel automatically. A 401 triggers one refresh + retry.
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** Error envelope from the API: `{"error": {code, message, details}}`. */
export type ApiError = { code: string; message: string; details: Record<string, unknown> };

const REFRESH_PATH = "/api/v1/auth/refresh";
const NO_RETRY = ["/api/v1/auth/"];

let refreshing: Promise<boolean> | null = null;

/** Rotate the refresh cookie once, sharing the call between concurrent 401s. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(REFRESH_PATH, { method: "POST", credentials: "same-origin" })
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const retryOn401: Middleware = {
  async onResponse({ request, response }) {
    if (response.status !== 401) return undefined;
    const path = new URL(request.url, window.location.origin).pathname;
    if (NO_RETRY.some((p) => path.startsWith(p))) return undefined;
    if (!(await refreshSession())) return undefined;
    return fetch(request.clone());
  },
};

function currentLocale(): string {
  if (typeof document === "undefined") return "sw";
  return document.documentElement.lang === "en" ? "en" : "sw";
}

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use(retryOn401);
api.use({
  onRequest({ request }) {
    request.headers.set("Accept-Language", currentLocale());
    return request;
  },
});

/** Pull the API error envelope out of an openapi-fetch `error` value. */
export function apiError(error: unknown): ApiError | null {
  if (error && typeof error === "object" && "error" in error) {
    const inner = (error as { error: unknown }).error;
    if (inner && typeof inner === "object" && "code" in inner) return inner as ApiError;
  }
  return null;
}
