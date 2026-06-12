"use client";

import { useSearchParams } from "next/navigation";

// Better Auth redirects OAuth failures back with ?error=<code>.
const MESSAGES: Record<string, string> = {
  account_not_linked:
    "This email is already registered with another sign-in method. Sign in the way you originally did.",
  signup_disabled: "Sign-ups are currently disabled.",
  access_denied: "You cancelled the sign-in.",
};

export function CallbackError() {
  const code = useSearchParams().get("error");
  if (!code) return null;
  return (
    <p className="text-center text-sm text-destructive">
      {MESSAGES[code] ?? `Sign-in failed (${code.replaceAll("_", " ")}). Please try again.`}
    </p>
  );
}
