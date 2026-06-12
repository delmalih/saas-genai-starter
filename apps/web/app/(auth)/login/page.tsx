import type { Metadata } from "next";
import Link from "next/link";
import { enabledSocialProviders } from "@/lib/auth";
import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { SocialButtons } from "@/components/auth/social-buttons";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AuthCard
      title="Welcome back"
      description="Sign in to your workspace"
      footer={
        <>
          No account yet?{" "}
          <Link href="/signup" className="text-foreground underline">
            Create one
          </Link>
        </>
      }
    >
      <SocialButtons providers={enabledSocialProviders} />
      <LoginForm />
    </AuthCard>
  );
}
