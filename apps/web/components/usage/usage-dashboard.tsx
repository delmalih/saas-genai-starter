"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { useOrg } from "@/components/org-provider";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface DailyCost {
  day: string;
  feature: string;
  model: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  calls: number;
}

interface UsageSummary {
  total_cost_usd: number;
  limits: {
    requests_per_minute: number;
    tokens_per_day: number;
    tokens_used_today: number;
  };
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});
const compact = new Intl.NumberFormat("en-US", { notation: "compact" });

function DailyChart({ daily }: { daily: DailyCost[] }) {
  const byDay = new Map<string, number>();
  for (const entry of daily) {
    byDay.set(entry.day, (byDay.get(entry.day) ?? 0) + entry.cost_usd);
  }
  const days = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(...days.map(([, cost]) => cost), 0.000001);

  return (
    <div className="flex h-36 items-end gap-1">
      {days.map(([day, cost]) => (
        <div
          key={day}
          className="group relative flex-1 rounded-t-sm bg-primary/70 transition-colors hover:bg-primary"
          style={{ height: `${Math.max((cost / max) * 100, 2)}%` }}
        >
          <span className="pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded border bg-popover px-1.5 py-0.5 text-xs group-hover:block">
            {day} · {usd.format(cost)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function UsageDashboard() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.id;

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/usage/summary");
      if (!data) {
        throw new Error(`Failed to load usage (${response.status})`);
      }
      return data as UsageSummary;
    },
  });

  const dailyQuery = useQuery({
    queryKey: ["usage-daily", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/usage/daily");
      if (!data) {
        throw new Error(`Failed to load usage (${response.status})`);
      }
      return data as DailyCost[];
    },
  });

  if (summaryQuery.isLoading || dailyQuery.isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  const summary = summaryQuery.data;
  const daily = dailyQuery.data ?? [];
  const tokensUsed = summary?.limits.tokens_used_today ?? 0;
  const tokensBudget = summary?.limits.tokens_per_day ?? 0;
  const budgetRatio = tokensBudget > 0 ? Math.min(tokensUsed / tokensBudget, 1) : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Cost — last 30 days</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {usd.format(summary?.total_cost_usd ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Tokens today</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {compact.format(tokensUsed)}
              <span className="text-sm font-normal text-muted-foreground">
                {" "}
                / {compact.format(tokensBudget)}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${budgetRatio * 100}%` }}
              />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Request limit</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {summary?.limits.requests_per_minute ?? 0}
              <span className="text-sm font-normal text-muted-foreground"> /min</span>
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Daily cost</CardTitle>
          <CardDescription>LLM spend per day, all features combined</CardDescription>
        </CardHeader>
        <CardContent>
          {daily.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No usage yet — start a conversation to see costs here.
            </p>
          ) : (
            <DailyChart daily={daily} />
          )}
        </CardContent>
      </Card>

      {daily.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Breakdown</CardTitle>
            <CardDescription>By day, feature and model</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 font-medium">Day</th>
                  <th className="py-2 font-medium">Feature</th>
                  <th className="py-2 font-medium">Model</th>
                  <th className="py-2 text-right font-medium">Calls</th>
                  <th className="py-2 text-right font-medium">Tokens in/out</th>
                  <th className="py-2 text-right font-medium">Cached</th>
                  <th className="py-2 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {daily.map((entry) => (
                  <tr
                    key={`${entry.day}-${entry.feature}-${entry.model}`}
                    className="border-b last:border-0"
                  >
                    <td className="py-2 tabular-nums">{entry.day}</td>
                    <td className="py-2">{entry.feature}</td>
                    <td className="py-2 text-muted-foreground">{entry.model}</td>
                    <td className="py-2 text-right tabular-nums">{entry.calls}</td>
                    <td className="py-2 text-right tabular-nums">
                      {compact.format(entry.input_tokens)} / {compact.format(entry.output_tokens)}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {compact.format(entry.cache_read_tokens)}
                    </td>
                    <td className="py-2 text-right tabular-nums">{usd.format(entry.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
