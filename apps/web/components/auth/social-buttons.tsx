"use client";

import { useState } from "react";
import { signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

// lucide-react carries no brand icons — minimal inline marks instead.
const ICONS: Record<string, React.ReactNode> = {
  google: (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="currentColor"
        d="M21.35 11.1h-9.17v2.73h6.51c-.33 3.81-3.5 5.44-6.5 5.44C8.36 19.27 5 16.25 5 12c0-4.1 3.2-7.27 7.2-7.27 3.09 0 4.9 1.97 4.9 1.97L19 4.72S16.56 2 12.1 2C6.42 2 2.03 6.8 2.03 12c0 5.05 4.13 10 10.22 10 5.35 0 9.25-3.67 9.25-9.09 0-1.15-.15-1.81-.15-1.81Z"
      />
    </svg>
  ),
  github: (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="currentColor"
        d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.55v-2.17c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.34.96.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 5.74 0c2.18-1.49 3.14-1.18 3.14-1.18.63 1.59.24 2.76.12 3.05.74.81 1.18 1.83 1.18 3.09 0 4.41-2.69 5.38-5.26 5.66.41.36.78 1.05.78 2.13v3.16c0 .3.2.66.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z"
      />
    </svg>
  ),
  apple: (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="currentColor"
        d="M16.36 12.78c.03 3.13 2.75 4.17 2.78 4.18-.02.07-.43 1.48-1.43 2.93-.86 1.26-1.76 2.51-3.17 2.54-1.39.03-1.84-.82-3.42-.82-1.59 0-2.08.79-3.4.85-1.36.05-2.4-1.36-3.27-2.61C2.66 17.3 1.32 12.62 3.14 9.5c.9-1.55 2.51-2.53 4.26-2.55 1.34-.03 2.6.9 3.42.9.82 0 2.35-1.11 3.96-.95.68.03 2.57.27 3.79 2.05-.1.06-2.26 1.32-2.21 3.83ZM13.74 5.18c.72-.87 1.2-2.08 1.07-3.28-1.04.04-2.29.69-3.03 1.56-.67.77-1.25 2-1.09 3.18 1.15.09 2.33-.59 3.05-1.46Z"
      />
    </svg>
  ),
};

const LABELS: Record<string, string> = {
  google: "Google",
  github: "GitHub",
  apple: "Apple",
};

export function SocialButtons({ providers }: { providers: string[] }) {
  const [pending, setPending] = useState<string | null>(null);
  if (providers.length === 0) return null;

  async function start(provider: string) {
    setPending(provider);
    // Full-page OAuth redirect; only reached again on error.
    const { error } = await signIn.social({ provider, callbackURL: "/chat" });
    if (error) setPending(null);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        {providers.map((provider) => (
          <Button
            key={provider}
            type="button"
            variant="outline"
            disabled={pending !== null}
            onClick={() => start(provider)}
          >
            {ICONS[provider]}
            {pending === provider
              ? "Redirecting…"
              : `Continue with ${LABELS[provider] ?? provider}`}
          </Button>
        ))}
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        or
        <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}
