import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

const googleEnabled =
  !!process.env.GOOGLE_CLIENT_ID && !!process.env.GOOGLE_CLIENT_SECRET;

export const auth = betterAuth({
  database: new Pool({
    // Pgbouncer poolers (e.g. Neon's) reject the search_path startup
    // parameter, so auth must connect directly. The Neon Vercel integration
    // injects DATABASE_URL_UNPOOLED; locally only DATABASE_URL is set.
    connectionString:
      process.env.DATABASE_URL_UNPOOLED ?? process.env.DATABASE_URL,
    // Auth tables live in their own schema, away from API-owned tables.
    options: "-c search_path=auth",
    // Direct (unpooled) connections are a scarce resource on managed
    // Postgres free tiers — keep the per-instance pool small.
    max: 3,
  }),
  emailAndPassword: {
    enabled: true,
    sendResetPassword: async ({ user, url }) => {
      // Real email delivery lands with SGS-014; until then the reset link
      // is only usable from the server logs in local dev.
      console.info(`Password reset for ${user.email}: ${url}`);
    },
  },
  socialProviders: googleEnabled
    ? {
        google: {
          clientId: process.env.GOOGLE_CLIENT_ID as string,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
        },
      }
    : undefined,
  plugins: [
    // Exposes /api/auth/jwks + /api/auth/token so the FastAPI backend can
    // validate sessions without sharing the auth database.
    jwt(),
    // Must be last: makes auth cookies work in Next.js server actions.
    nextCookies(),
  ],
});

export { googleEnabled };
