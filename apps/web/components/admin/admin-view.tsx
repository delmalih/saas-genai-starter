"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

interface AdminOrganization {
  id: string;
  name: string;
  created_at: string;
  members: number;
  documents: number;
  conversations: number;
  cost_30d_usd: number;
  rate_limit_rpm_override: number | null;
  rate_limit_tpd_override: number | null;
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

function LimitsEditor({ organization }: { organization: AdminOrganization }) {
  const queryClient = useQueryClient();
  const [rpm, setRpm] = useState(organization.rate_limit_rpm_override?.toString() ?? "");
  const [tpd, setTpd] = useState(organization.rate_limit_tpd_override?.toString() ?? "");

  const save = useMutation({
    mutationFn: async () => {
      await api.PATCH("/admin/organizations/{organization_id}/limits", {
        params: { path: { organization_id: organization.id } },
        body: {
          requests_per_minute: rpm === "" ? null : Number(rpm),
          tokens_per_day: tpd === "" ? null : Number(tpd),
        },
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-orgs"] }),
  });

  return (
    <div className="flex items-center gap-1.5">
      <Input
        value={rpm}
        onChange={(event) => setRpm(event.target.value)}
        placeholder="req/min"
        className="h-8 w-20 text-xs"
        inputMode="numeric"
      />
      <Input
        value={tpd}
        onChange={(event) => setTpd(event.target.value)}
        placeholder="tok/day"
        className="h-8 w-24 text-xs"
        inputMode="numeric"
      />
      <Button size="sm" variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>
        Set
      </Button>
    </div>
  );
}

export function AdminView() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-orgs"],
    retry: false,
    queryFn: async () => {
      const { data: payload, response } = await api.GET("/admin/organizations");
      if (response.status === 404) {
        throw new Error("not-admin");
      }
      if (!payload) {
        throw new Error(`Failed to load (${response.status})`);
      }
      return payload as AdminOrganization[];
    },
  });

  if (isLoading) {
    return <Skeleton className="h-48 w-full" />;
  }
  // Same face as a missing route — the admin surface stays invisible.
  if (error) {
    return <p className="pt-24 text-center text-sm text-muted-foreground">404 — Not found</p>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organizations</CardTitle>
        <CardDescription>
          Every workspace on this deployment. Empty limit fields fall back to server
          defaults.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 font-medium">Organization</th>
              <th className="py-2 text-right font-medium">Members</th>
              <th className="py-2 text-right font-medium">Docs</th>
              <th className="py-2 text-right font-medium">Convos</th>
              <th className="py-2 text-right font-medium">Cost 30d</th>
              <th className="py-2 pl-4 font-medium">Rate limits</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((organization) => (
              <tr key={organization.id} className="border-b last:border-0">
                <td className="py-2 font-medium">{organization.name}</td>
                <td className="py-2 text-right tabular-nums">{organization.members}</td>
                <td className="py-2 text-right tabular-nums">{organization.documents}</td>
                <td className="py-2 text-right tabular-nums">{organization.conversations}</td>
                <td className="py-2 text-right tabular-nums">
                  {usd.format(organization.cost_30d_usd)}
                </td>
                <td className="py-2 pl-4">
                  <LimitsEditor organization={organization} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
