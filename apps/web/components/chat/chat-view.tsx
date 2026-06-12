"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { SendIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { streamChatMessage } from "@/lib/api/chat-stream";
import { useOrg } from "@/components/org-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ConversationDetail {
  id: string;
  title: string;
  messages: ChatMessage[];
}

function MessageBubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
          role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function ChatView({ conversationId }: { conversationId: string | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { activeOrg } = useOrg();
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const isBusy = streamingText !== null || pendingUser !== null;

  const { data: detail } = useQuery({
    queryKey: ["conversation", activeOrg?.id, conversationId],
    enabled: !!conversationId && !!activeOrg,
    queryFn: async () => {
      const { data, response } = await api.GET("/conversations/{conversation_id}", {
        params: { path: { conversation_id: conversationId! } },
      });
      if (!data) {
        throw new Error(`Failed to load the conversation (${response.status})`);
      }
      return data as ConversationDetail;
    },
  });

  const messages = detail?.messages ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  async function send() {
    const content = input.trim();
    if (!content || isBusy) {
      return;
    }
    setInput("");
    setError(null);
    setPendingUser(content);
    try {
      let targetId = conversationId;
      let created = false;
      if (!targetId) {
        const { data } = await api.POST("/conversations", { body: {} });
        if (!data) {
          throw new Error("Could not create the conversation");
        }
        targetId = data.id;
        created = true;
      }

      setStreamingText("");
      for await (const event of streamChatMessage(targetId, content)) {
        if (event.type === "delta") {
          setStreamingText((previous) => (previous ?? "") + event.text);
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      }

      await queryClient.invalidateQueries({ queryKey: ["conversation", activeOrg?.id, targetId] });
      await queryClient.invalidateQueries({ queryKey: ["conversations", activeOrg?.id] });
      if (created) {
        router.push(`/chat/${targetId}`);
      }
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Something went wrong");
    } finally {
      setPendingUser(null);
      setStreamingText(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-6">
          {messages.length === 0 && !pendingUser ? (
            <div className="pt-24 text-center text-sm text-muted-foreground">
              Start a conversation — replies stream in real time.
            </div>
          ) : null}
          {messages.map((message) => (
            <MessageBubble key={message.id} role={message.role}>
              {message.content}
            </MessageBubble>
          ))}
          {pendingUser ? <MessageBubble role="user">{pendingUser}</MessageBubble> : null}
          {streamingText !== null ? (
            <MessageBubble role="assistant">
              {streamingText || <span className="animate-pulse">…</span>}
            </MessageBubble>
          ) : null}
          {error ? <p className="text-center text-sm text-destructive">{error}</p> : null}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="border-t bg-background p-4">
        <form
          className="mx-auto flex w-full max-w-2xl items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            placeholder="Message the assistant…"
            rows={2}
            className="flex-1 resize-none rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button type="submit" size="icon" disabled={isBusy || !input.trim()} aria-label="Send">
            <SendIcon className="size-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}
