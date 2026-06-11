"use client";

import { useMutation } from "@tanstack/react-query";
import { Building2Icon, CheckIcon, ChevronsUpDownIcon, PlusIcon } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api/client";
import { useOrg } from "@/components/org-provider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

function CreateOrgDialog({ onCreated }: { onCreated: (orgId: string) => void }) {
  const [open, setOpen] = useState(false);
  const { refreshOrgs } = useOrg();

  const createOrg = useMutation({
    mutationFn: async (name: string) => {
      const { data, response } = await api.POST("/organizations", { body: { name } });
      if (!data) {
        throw new Error(`Could not create the organization (${response.status})`);
      }
      return data;
    },
    onSuccess: async (org) => {
      await refreshOrgs();
      onCreated(org.id);
      setOpen(false);
    },
  });

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = new FormData(event.currentTarget).get("name") as string;
    createOrg.mutate(name);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="flex w-full items-center gap-2 px-2 py-1.5 text-sm">
          <PlusIcon className="size-4" />
          New organization
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create an organization</DialogTitle>
          <DialogDescription>A shared workspace for your team.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="org-name">Name</Label>
            <Input id="org-name" name="name" required minLength={1} maxLength={120} />
          </div>
          {createOrg.isError ? (
            <p className="text-sm text-destructive">{createOrg.error.message}</p>
          ) : null}
          <Button type="submit" disabled={createOrg.isPending}>
            {createOrg.isPending ? "Creating…" : "Create"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function OrgSwitcher() {
  const { organizations, activeOrg, switchOrg, isLoading } = useOrg();

  if (isLoading) {
    return <Skeleton className="h-9 w-full" />;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium outline-none hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring">
        <Building2Icon className="size-4 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-left">
          {activeOrg?.name ?? "Select organization"}
        </span>
        <ChevronsUpDownIcon className="size-4 shrink-0 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        {organizations.map((org) => (
          <DropdownMenuItem key={org.id} onSelect={() => switchOrg(org.id)}>
            <span className="flex-1 truncate">{org.name}</span>
            {org.id === activeOrg?.id ? <CheckIcon className="size-4" /> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <CreateOrgDialog onCreated={switchOrg} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
