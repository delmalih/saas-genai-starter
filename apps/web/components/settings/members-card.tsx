"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2Icon } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

interface Member {
  user_id: string;
  role: "owner" | "admin" | "member";
  email: string | null;
  name: string | null;
}

interface Invitation {
  id: string;
  email: string;
  role: "owner" | "admin" | "member";
  expires_at: string;
}

export function MembersCard() {
  const { activeOrg } = useOrg();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const orgId = activeOrg?.id;
  const isAdmin = activeOrg?.role === "owner" || activeOrg?.role === "admin";

  const membersQuery = useQuery({
    queryKey: ["members", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/organizations/{organization_id}/members", {
        params: { path: { organization_id: orgId! } },
      });
      if (!data) {
        throw new Error(`Failed to load members (${response.status})`);
      }
      return data as Member[];
    },
  });

  const invitationsQuery = useQuery({
    queryKey: ["invitations", orgId],
    enabled: !!orgId && isAdmin,
    queryFn: async () => {
      const { data, response } = await api.GET(
        "/organizations/{organization_id}/invitations",
        { params: { path: { organization_id: orgId! } } },
      );
      if (!data) {
        throw new Error(`Failed to load invitations (${response.status})`);
      }
      return data as Invitation[];
    },
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["members", orgId] });
    queryClient.invalidateQueries({ queryKey: ["invitations", orgId] });
  }

  const invite = useMutation({
    mutationFn: async (input: { email: string; role: "admin" | "member" }) => {
      const { data, error, response } = await api.POST(
        "/organizations/{organization_id}/invitations",
        { params: { path: { organization_id: orgId! } }, body: input },
      );
      if (!data) {
        throw new Error(errorMessage(error, `Invitation failed (${response.status})`));
      }
      return data;
    },
    onSuccess: (invitation) => {
      setFeedback(`Invitation sent to ${invitation.email}.`);
      refresh();
    },
    onError: (mutationError) => setFeedback(mutationError.message),
  });

  const changeRole = useMutation({
    mutationFn: async (input: { userId: string; role: "owner" | "admin" | "member" }) => {
      const { data, error, response } = await api.PATCH(
        "/organizations/{organization_id}/members/{member_user_id}",
        {
          params: {
            path: { organization_id: orgId!, member_user_id: input.userId },
          },
          body: { role: input.role },
        },
      );
      if (!data) {
        throw new Error(errorMessage(error, `Role update failed (${response.status})`));
      }
      return data;
    },
    onSuccess: refresh,
    onError: (mutationError) => setFeedback(mutationError.message),
  });

  const removeMember = useMutation({
    mutationFn: async (userId: string) => {
      const { error, response } = await api.DELETE(
        "/organizations/{organization_id}/members/{member_user_id}",
        { params: { path: { organization_id: orgId!, member_user_id: userId } } },
      );
      if (!response.ok) {
        throw new Error(errorMessage(error, `Removal failed (${response.status})`));
      }
    },
    onSuccess: refresh,
    onError: (mutationError) => setFeedback(mutationError.message),
  });

  const revokeInvitation = useMutation({
    mutationFn: async (invitationId: string) => {
      const { error, response } = await api.DELETE(
        "/organizations/{organization_id}/invitations/{invitation_id}",
        { params: { path: { organization_id: orgId!, invitation_id: invitationId } } },
      );
      if (!response.ok) {
        throw new Error(errorMessage(error, `Revoke failed (${response.status})`));
      }
    },
    onSuccess: refresh,
    onError: (mutationError) => setFeedback(mutationError.message),
  });

  function handleInvite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback(null);
    const formData = new FormData(event.currentTarget);
    invite.mutate({
      email: formData.get("email") as string,
      role: formData.get("role") as "admin" | "member",
    });
    event.currentTarget.reset();
  }

  if (!activeOrg) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>People with access to {activeOrg.name}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {membersQuery.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <ul className="flex flex-col divide-y">
            {(membersQuery.data ?? []).map((member) => (
              <li key={member.user_id} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {member.name ?? member.email ?? member.user_id}
                  </p>
                  {member.email ? (
                    <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                  ) : null}
                </div>
                {isAdmin ? (
                  <Select
                    value={member.role}
                    onValueChange={(role) =>
                      changeRole.mutate({
                        userId: member.user_id,
                        role: role as "owner" | "admin" | "member",
                      })
                    }
                  >
                    <SelectTrigger className="w-28" size="sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="owner" disabled={activeOrg.role !== "owner"}>
                        owner
                      </SelectItem>
                      <SelectItem value="admin">admin</SelectItem>
                      <SelectItem value="member">member</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <span className="text-sm text-muted-foreground">{member.role}</span>
                )}
                {isAdmin ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${member.email ?? member.user_id}`}
                    onClick={() => removeMember.mutate(member.user_id)}
                  >
                    <Trash2Icon className="size-4" />
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {isAdmin ? (
          <>
            <form onSubmit={handleInvite} className="flex max-w-xl items-end gap-2 border-t pt-5">
              <div className="flex flex-1 flex-col gap-2">
                <label
                  htmlFor="invite-email"
                  className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                >
                  Invite by email
                </label>
                <Input
                  id="invite-email"
                  name="email"
                  type="email"
                  placeholder="teammate@company.com"
                  required
                />
              </div>
              <Select name="role" defaultValue="member">
                <SelectTrigger className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">admin</SelectItem>
                  <SelectItem value="member">member</SelectItem>
                </SelectContent>
              </Select>
              <Button type="submit" disabled={invite.isPending}>
                {invite.isPending ? "Sending…" : "Invite"}
              </Button>
            </form>

            {(invitationsQuery.data ?? []).length > 0 ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Pending invitations
                </p>
                <ul className="flex flex-col divide-y">
                  {(invitationsQuery.data ?? []).map((invitation) => (
                    <li key={invitation.id} className="flex items-center gap-3 py-2">
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {invitation.email}
                      </span>
                      <span className="text-xs text-muted-foreground">{invitation.role}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => revokeInvitation.mutate(invitation.id)}
                      >
                        Revoke
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}

        {feedback ? <p className="text-sm text-muted-foreground">{feedback}</p> : null}
      </CardContent>
    </Card>
  );
}
