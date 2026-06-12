import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

// Optimistic gate: presence of the session cookie only. Real session
// validation happens server-side (Better Auth) and in the API (JWT).
export function middleware(request: NextRequest) {
  const sessionCookie = getSessionCookie(request);
  if (!sessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/chat/:path*",
    "/documents/:path*",
    "/usage/:path*",
    "/settings/:path*",
    "/invite/:path*",
    "/admin/:path*",
  ],
};
