import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

// Each SSO provider activates when its env pair is set — none is required,
// email/password always works.
const socialProviderConfig = {
  google: {
    clientId: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
  },
  github: {
    clientId: process.env.GITHUB_CLIENT_ID,
    clientSecret: process.env.GITHUB_CLIENT_SECRET,
  },
  apple: {
    clientId: process.env.APPLE_CLIENT_ID,
    clientSecret: process.env.APPLE_CLIENT_SECRET,
  },
};

const enabledSocialProviders = Object.entries(socialProviderConfig)
  .filter(([, config]) => !!config.clientId && !!config.clientSecret)
  .map(([id]) => id);

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
  socialProviders: Object.fromEntries(
    enabledSocialProviders.map((id) => [
      id,
      {
        clientId: socialProviderConfig[id as keyof typeof socialProviderConfig]
          .clientId as string,
        clientSecret: socialProviderConfig[id as keyof typeof socialProviderConfig]
          .clientSecret as string,
      },
    ]),
  ),
  account: {
    // SSO sign-in with an email that already has an account links the new
    // provider to it (verified-email providers only) instead of failing.
    accountLinking: {
      enabled: true,
      trustedProviders: enabledSocialProviders,
      // Password signups are never email-verified in this starter (no
      // verification flow), so the default `true` would reject every link
      // with `account_not_linked`. Trade-off: someone who pre-registered a
      // victim's email with a password keeps that password after the victim
      // links via SSO. Flip to true if you wire signup email verification.
      requireLocalEmailVerified: false,
    },
  },
  plugins: [
    // Exposes /api/auth/jwks + /api/auth/token so the FastAPI backend can
    // validate sessions without sharing the auth database.
    jwt(),
    // Must be last: makes auth cookies work in Next.js server actions.
    nextCookies(),
  ],
});

export { enabledSocialProviders };
