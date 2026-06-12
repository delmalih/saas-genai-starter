import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { enabledSocialProviders } from "@/lib/auth";
import { AuthCard } from "@/components/auth/auth-card";
import { CallbackError } from "@/components/auth/callback-error";
import { SignupForm } from "@/components/auth/signup-form";
import { SocialButtons } from "@/components/auth/social-buttons";

export const metadata: Metadata = { title: "Create account" };

export default function SignupPage() {
  return (
    <AuthCard
      title="Create your account"
      description="Start with a personal workspace — invite your team later"
      footer={
        <>
          Already registered?{" "}
          <Link href="/login" className="text-foreground underline">
            Sign in
          </Link>
        </>
      }
    >
      {/* useSearchParams needs a Suspense boundary on statically rendered pages */}
      <Suspense fallback={null}>
        <CallbackError />
      </Suspense>
      <SocialButtons providers={enabledSocialProviders} />
      <SignupForm />
    </AuthCard>
  );
}
