"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function OrgSettingsCard() {
  const { activeOrg, refreshOrgs } = useOrg();
  const [feedback, setFeedback] = useState<string | null>(null);
  const canRename = activeOrg?.role === "owner" || activeOrg?.role === "admin";

  const rename = useMutation({
    mutationFn: async (name: string) => {
      const { data, error, response } = await api.PATCH("/organizations/{organization_id}", {
        params: { path: { organization_id: activeOrg!.id } },
        body: { name },
      });
      if (!data) {
        throw new Error(errorMessage(error, `Rename failed (${response.status})`));
      }
      return data;
    },
    onSuccess: async () => {
      setFeedback("Saved.");
      await refreshOrgs();
    },
    onError: (mutationError) => setFeedback(mutationError.message),
  });

  if (!activeOrg) {
    return null;
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback(null);
    rename.mutate(new FormData(event.currentTarget).get("name") as string);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organization</CardTitle>
        <CardDescription>
          Your role here: <span className="font-medium">{activeOrg.role}</span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex max-w-md items-end gap-2">
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="org-rename">Name</Label>
            <Input
              id="org-rename"
              name="name"
              key={activeOrg.id}
              defaultValue={activeOrg.name}
              disabled={!canRename}
              required
              maxLength={120}
            />
          </div>
          <Button type="submit" disabled={!canRename || rename.isPending}>
            Save
          </Button>
        </form>
        {feedback ? <p className="mt-2 text-sm text-muted-foreground">{feedback}</p> : null}
      </CardContent>
    </Card>
  );
}
