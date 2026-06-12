import type { Metadata } from "next";
import { AdminView } from "@/components/admin/admin-view";

export const metadata: Metadata = { title: "Admin" };

// Not linked from the sidebar on purpose — platform admins know the URL,
// everyone else gets a 404-shaped page (the API enforces the allowlist).
export default function AdminPage() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-2">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Platform admin</h1>
        <p className="text-sm text-muted-foreground">
          Cross-tenant overview — visible to allowlisted admins only.
        </p>
      </div>
      <AdminView />
    </div>
  );
}
