"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import { useOrg } from "@/components/org-provider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function AcceptInvitation({ token }: { token: string }) {
  const router = useRouter();
  const { refreshOrgs, switchOrg } = useOrg();

  const accept = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/invitations/accept", {
        body: { token },
      });
      if (!data) {
        throw new Error(
          errorMessage(error, `Could not accept the invitation (${response.status})`),
        );
      }
      return data;
    },
    onSuccess: async (accepted) => {
      await refreshOrgs();
      switchOrg(accepted.organization_id);
      router.push("/chat");
    },
  });

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle>You have been invited</CardTitle>
        <CardDescription>
          Accept to join the workspace with the role you were invited with.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
          {accept.isPending ? "Joining…" : "Accept invitation"}
        </Button>
        {accept.isError ? (
          <p className="text-center text-sm text-destructive">{accept.error.message}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
