import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

// Pages that only make sense without a session.
const GUEST_ONLY = ["/login", "/signup", "/forgot-password"];

// Optimistic gate: presence of the session cookie only. Real session
// validation happens server-side (Better Auth) and in the API (JWT).
export function middleware(request: NextRequest) {
  const sessionCookie = getSessionCookie(request);

  if (GUEST_ONLY.includes(request.nextUrl.pathname)) {
    if (!sessionCookie) {
      return NextResponse.next();
    }
    // Already signed in — honor ?from= (same-origin paths only), else home.
    const from = request.nextUrl.searchParams.get("from");
    const target = from?.startsWith("/") && !from.startsWith("//") ? from : "/chat";
    return NextResponse.redirect(new URL(target, request.url));
  }

  if (!sessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/login",
    "/signup",
    "/forgot-password",
    "/chat/:path*",
    "/documents/:path*",
    "/usage/:path*",
    "/settings/:path*",
    "/invite/:path*",
    "/admin/:path*",
  ],
};
