import type { Metadata } from "next";
import { MembersCard } from "@/components/settings/members-card";
import { OrgSettingsCard } from "@/components/settings/org-settings-card";
import { ProfileCard } from "@/components/settings/profile-card";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <h1 className="font-heading text-2xl font-semibold tracking-tight">Settings</h1>
      <ProfileCard />
      <OrgSettingsCard />
      <MembersCard />
    </div>
  );
}
