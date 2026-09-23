import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// The whole site sits behind one password, asked for on arrival rather than at
// the moment you press Generate.
//
// The cookie is httpOnly, so the page's own JavaScript cannot read it back —
// which is the point: the browser presents it, the server decides. Checking
// here rather than in each page means a route added later is covered by
// default instead of by remembering to gate it.

export const AUTH_COOKIE = "brief_auth";

// Paths that must answer before anyone has a cookie.
//
// /api/revalidate is on this list deliberately: the generators call it with
// their own shared secret to refresh a section after publishing, and gating it
// would break every issue's appearance without any error a reader could see.
// /api/cron likewise: Vercel Cron carries CRON_SECRET, never a cookie.
const OPEN = [
  "/enter",
  "/api/auth",
  "/api/revalidate",
  "/api/cron",
  "/offline", // the service worker's fallback page
  "/manifest.webmanifest",
  "/sw.js",
  "/robots.txt",
  "/sitemap.xml",
];

function isOpen(pathname: string): boolean {
  if (OPEN.includes(pathname)) return true;
  // Build output and icons: blocking these leaves a login page with no styles.
  return (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/icons/") ||
    pathname.startsWith("/splash/") ||
    pathname === "/favicon.ico" ||
    pathname === "/apple-touch-icon.png"
  );
}

export function middleware(request: NextRequest) {
  const password = process.env.SITE_PASSWORD ?? process.env.GENERATE_PASSWORD;
  // No password configured means no gate. A deployment that forgot the
  // variable should serve the site, not lock everyone out of it.
  if (!password) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  if (isOpen(pathname)) return NextResponse.next();

  if (request.cookies.get(AUTH_COOKIE)?.value === password) {
    return NextResponse.next();
  }

  // An API call gets a status it can act on; a page gets the login screen.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  const url = request.nextUrl.clone();
  url.pathname = "/enter";
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
