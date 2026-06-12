import type { Metadata } from "next";
import Link from "next/link";
import { enabledSocialProviders } from "@/lib/auth";
import { AuthCard } from "@/components/auth/auth-card";
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
      <SocialButtons providers={enabledSocialProviders} />
      <SignupForm />
    </AuthCard>
  );
}
