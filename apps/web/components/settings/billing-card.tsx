"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2Icon, SparklesIcon } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import { useOrg } from "@/components/org-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Billing {
  enabled: boolean;
  plan: string;
  subscription_status: string | null;
  can_manage: boolean;
}

export function BillingCard() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.id;

  const billingQuery = useQuery({
    queryKey: ["billing", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/billing");
      if (!data) throw new Error(`Failed to load billing (${response.status})`);
      return data as Billing;
    },
  });

  const checkout = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/billing/checkout");
      if (!data) throw new Error(errorMessage(error, `Checkout failed (${response.status})`));
      return data as { url: string };
    },
    onSuccess: ({ url }) => window.location.assign(url),
  });

  const portal = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/billing/portal");
      if (!data) throw new Error(errorMessage(error, `Portal failed (${response.status})`));
      return data as { url: string };
    },
    onSuccess: ({ url }) => window.location.assign(url),
  });

  const billing = billingQuery.data;
  // The whole card disappears when the deployment has billing turned off.
  if (!billing?.enabled) return null;

  const isPro = billing.plan === "pro";
  const pending = checkout.isPending || portal.isPending;
  const actionError = checkout.error ?? portal.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Billing
          <Badge variant={isPro ? "default" : "secondary"}>
            {isPro ? "Pro" : "Free"}
          </Badge>
        </CardTitle>
        <CardDescription>
          {isPro
            ? "Your organization is on the Pro plan with raised rate limits."
            : "Upgrade to the Pro plan for higher request and token limits."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-2">
        {isPro ? (
          <Button
            variant="outline"
            disabled={!billing.can_manage || pending}
            onClick={() => portal.mutate()}
          >
            {portal.isPending ? <Loader2Icon className="size-4 animate-spin" /> : null}
            Manage subscription
          </Button>
        ) : (
          <Button disabled={!billing.can_manage || pending} onClick={() => checkout.mutate()}>
            {checkout.isPending ? (
              <Loader2Icon className="size-4 animate-spin" />
            ) : (
              <SparklesIcon className="size-4" />
            )}
            Upgrade to Pro
          </Button>
        )}
        {!billing.can_manage ? (
          <p className="text-sm text-muted-foreground">
            Only owners and admins can manage billing.
          </p>
        ) : null}
        {actionError ? (
          <p className="text-sm text-destructive">{actionError.message}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
