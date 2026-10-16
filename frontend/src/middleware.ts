import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

const intl = createMiddleware(routing);

const ACCESS = "access_token";
const REFRESH = "refresh_token";
const apiTarget = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

/**
 * The access cookie lives 15 minutes. When it has expired but a refresh cookie is present,
 * rotate the session and redirect to the same URL so the page renders signed in.
 */
async function renewSession(req: NextRequest): Promise<NextResponse | null> {
  const refresh = req.cookies.get(REFRESH)?.value;
  if (!refresh || req.cookies.has(ACCESS) || !["GET", "HEAD"].includes(req.method)) return null;
  try {
    const res = await fetch(`${apiTarget}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { cookie: `${REFRESH}=${refresh}` },
      cache: "no-store",
    });
    const redirect = NextResponse.redirect(req.nextUrl, 307);
    if (res.ok) {
      for (const cookie of res.headers.getSetCookie()) redirect.headers.append("set-cookie", cookie);
    } else {
      redirect.cookies.delete(REFRESH); // revoked or expired: stop retrying
    }
    return redirect;
  } catch {
    return null; // API unreachable: render signed out
  }
}

export default async function middleware(req: NextRequest) {
  return (await renewSession(req)) ?? intl(req);
}

export const config = {
  // Everything except the API proxy, Next internals and files with an extension.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
