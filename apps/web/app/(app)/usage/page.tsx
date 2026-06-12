import type { Metadata } from "next";
import { UsageDashboard } from "@/components/usage/usage-dashboard";

export const metadata: Metadata = { title: "Usage" };

export default function UsagePage() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-2">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Usage</h1>
        <p className="text-sm text-muted-foreground">
          LLM costs and token consumption for this workspace.
        </p>
      </div>
      <UsageDashboard />
    </div>
  );
}
