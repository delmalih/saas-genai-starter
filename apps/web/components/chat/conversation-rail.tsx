"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { useOrg } from "@/components/org-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export function ConversationRail() {
  const { activeOrg } = useOrg();
  const params = useParams<{ id?: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const orgId = activeOrg?.id;

  const { data: conversations, isLoading } = useQuery({
    queryKey: ["conversations", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/conversations");
      if (!data) {
        throw new Error(`Failed to load conversations (${response.status})`);
      }
      return data as Conversation[];
    },
  });

  const deleteConversation = useMutation({
    mutationFn: async (conversationId: string) => {
      await api.DELETE("/conversations/{conversation_id}", {
        params: { path: { conversation_id: conversationId } },
      });
    },
    onSuccess: (_, conversationId) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
      if (params.id === conversationId) {
        router.push("/chat");
      }
    },
  });

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r">
      <div className="p-3">
        <Button asChild variant="outline" size="sm" className="w-full justify-start">
          <Link href="/chat">
            <PlusIcon className="size-4" />
            New chat
          </Link>
        </Button>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {isLoading ? (
          <div className="flex flex-col gap-2 px-1">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : (
          (conversations ?? []).map((conversation) => (
            <div
              key={conversation.id}
              className={cn(
                "group flex items-center rounded-md text-sm",
                params.id === conversation.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <Link
                href={`/chat/${conversation.id}`}
                className="min-w-0 flex-1 truncate px-3 py-2"
              >
                {conversation.title}
              </Link>
              <button
                aria-label={`Delete ${conversation.title}`}
                className="invisible pr-2 text-muted-foreground hover:text-destructive group-hover:visible"
                onClick={() => deleteConversation.mutate(conversation.id)}
              >
                <Trash2Icon className="size-3.5" />
              </button>
            </div>
          ))
        )}
      </nav>
    </aside>
  );
}
