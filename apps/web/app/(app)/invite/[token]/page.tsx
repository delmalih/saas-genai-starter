import type { Metadata } from "next";
import { AcceptInvitation } from "@/components/accept-invitation";

export const metadata: Metadata = { title: "Invitation" };

export default async function InvitePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <div className="mx-auto w-full max-w-md pt-12">
      <AcceptInvitation token={token} />
    </div>
  );
}
