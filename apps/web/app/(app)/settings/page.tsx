import type { Metadata } from "next";
import { AIProviderCard } from "@/components/settings/ai-provider-card";
import { BillingCard } from "@/components/settings/billing-card";
import { MembersCard } from "@/components/settings/members-card";
import { OrgSettingsCard } from "@/components/settings/org-settings-card";
import { ProfileCard } from "@/components/settings/profile-card";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-2">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your account and workspace.
        </p>
      </div>
      <ProfileCard />
      <AIProviderCard />
      <BillingCard />
      <OrgSettingsCard />
      <MembersCard />
    </div>
  );
}
