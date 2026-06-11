"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import { getActiveOrgId, setActiveOrgId } from "@/lib/org-store";

export interface Organization {
  id: string;
  name: string;
  role: "owner" | "admin" | "member";
  created_at: string;
}

interface OrgContextValue {
  organizations: Organization[];
  activeOrg: Organization | null;
  switchOrg: (orgId: string) => void;
  refreshOrgs: () => Promise<unknown>;
  isLoading: boolean;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function useOrg(): OrgContextValue {
  const value = useContext(OrgContext);
  if (!value) {
    throw new Error("useOrg must be used inside OrgProvider");
  }
  return value;
}

function OrgContextProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [activeOrgId, setActiveOrgIdState] = useState<string | null>(getActiveOrgId);

  const { data: organizations = [], isLoading, refetch } = useQuery({
    queryKey: ["organizations"],
    queryFn: async () => {
      const { data, response } = await api.GET("/organizations");
      if (!data) {
        throw new Error(`Failed to load organizations (${response.status})`);
      }
      return data as Organization[];
    },
  });

  const activeOrg = useMemo(() => {
    if (organizations.length === 0) {
      return null;
    }
    const found = organizations.find((org) => org.id === activeOrgId);
    if (found) {
      return found;
    }
    // First load (or stale stored id): fall back to the first organization.
    setActiveOrgId(organizations[0].id);
    return organizations[0];
  }, [organizations, activeOrgId]);

  const switchOrg = useCallback(
    (orgId: string) => {
      setActiveOrgId(orgId);
      setActiveOrgIdState(orgId);
      // All tenant-scoped queries must refetch under the new X-Org-Id.
      queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const value = useMemo(
    () => ({
      organizations,
      activeOrg,
      switchOrg,
      refreshOrgs: refetch,
      isLoading,
    }),
    [organizations, activeOrg, switchOrg, refetch, isLoading],
  );

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <OrgContextProvider>{children}</OrgContextProvider>
    </QueryClientProvider>
  );
}
