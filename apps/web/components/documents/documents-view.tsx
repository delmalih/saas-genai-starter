"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileTextIcon, Loader2Icon, Trash2Icon, UploadIcon } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { uploadDocument } from "@/lib/api/upload";
import { useOrg } from "@/components/org-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface Document {
  id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "ready" | "failed";
  error: string | null;
  title: string | null;
  summary: string | null;
  topics: string[] | null;
  created_at: string;
}

const statusStyles: Record<Document["status"], string> = {
  uploaded: "bg-muted text-muted-foreground",
  processing: "bg-blue-500/15 text-blue-500",
  ready: "bg-emerald-500/15 text-emerald-500",
  failed: "bg-destructive/15 text-destructive",
};

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function DocumentsView() {
  const { activeOrg } = useOrg();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const orgId = activeOrg?.id;

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/documents");
      if (!data) {
        throw new Error(`Failed to load documents (${response.status})`);
      }
      return data as Document[];
    },
    // Poll while anything is still being ingested.
    refetchInterval: (query) =>
      (query.state.data ?? []).some(
        (d) => d.status === "uploaded" || d.status === "processing",
      )
        ? 2500
        : false,
  });

  const upload = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["documents", orgId] });
    },
    onError: (uploadError) => setError(uploadError.message),
  });

  const remove = useMutation({
    mutationFn: async (documentId: string) => {
      await api.DELETE("/documents/{document_id}", {
        params: { path: { document_id: documentId } },
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", orgId] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          PDF, TXT or Markdown — up to 20 MB. Ready documents become searchable in chat.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              upload.mutate(file);
            }
            event.target.value = "";
          }}
        />
        <Button onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
          {upload.isPending ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <UploadIcon className="size-4" />
          )}
          Upload
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : (documents ?? []).length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No documents yet — upload one to start chatting with your content.
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {(documents ?? []).map((document) => (
            <li key={document.id}>
              <Card>
                <CardContent className="flex items-start gap-3 py-4">
                  <FileTextIcon className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium">
                        {document.title ?? document.name}
                      </p>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          statusStyles[document.status],
                        )}
                      >
                        {document.status}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {document.name} · {formatSize(document.size_bytes)}
                    </p>
                    {document.summary ? (
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {document.summary}
                      </p>
                    ) : null}
                    {document.error ? (
                      <p className="mt-1 text-sm text-destructive">{document.error}</p>
                    ) : null}
                    {document.topics?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {document.topics.map((topic) => (
                          <span
                            key={topic}
                            className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground"
                          >
                            {topic}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${document.name}`}
                    onClick={() => remove.mutate(document.id)}
                  >
                    <Trash2Icon className="size-4" />
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
