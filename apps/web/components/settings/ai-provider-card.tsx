"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, Loader2Icon, XCircleIcon } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

interface KeyState {
  is_set: boolean;
  last4: string | null;
}

interface LLMSettings {
  chat_provider: string;
  chat_model: string;
  embedding_provider: string;
  keys: Record<string, KeyState>;
}

interface Catalog {
  chat_providers: {
    id: string;
    label: string;
    models: string[];
    default_model: string;
    key_field: string;
  }[];
  embedding_providers: { id: string; label: string; model: string; key_field: string }[];
}

const KEY_LABELS: Record<string, string> = {
  anthropic_api_key: "Anthropic API key",
  openai_api_key: "OpenAI API key",
  voyage_api_key: "Voyage AI API key",
  gemini_api_key: "Google Gemini API key",
  mistral_api_key: "Mistral API key",
  xai_api_key: "xAI API key",
  deepseek_api_key: "DeepSeek API key",
  groq_api_key: "Groq API key",
  openrouter_api_key: "OpenRouter API key",
  cohere_api_key: "Cohere API key",
};

function KeyInput({
  field,
  state,
  value,
  disabled,
  onChange,
  onClear,
}: {
  field: string;
  state: KeyState | undefined;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={field}>{KEY_LABELS[field] ?? field}</Label>
      <div className="flex items-center gap-2">
        <Input
          id={field}
          type="password"
          autoComplete="off"
          placeholder={
            state?.is_set ? `Configured (••••${state.last4}) — paste to replace` : "sk-..."
          }
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        {state?.is_set ? (
          <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={onClear}>
            Remove
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function AIProviderCard() {
  const { activeOrg } = useOrg();
  const queryClient = useQueryClient();
  const orgId = activeOrg?.id;
  const canEdit = activeOrg?.role === "owner" || activeOrg?.role === "admin";

  const [chatProvider, setChatProvider] = useState<string | null>(null);
  const [chatModel, setChatModel] = useState<string | null>(null);
  const [embeddingProvider, setEmbeddingProvider] = useState<string | null>(null);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string | null } | null>(
    null,
  );

  const catalogQuery = useQuery({
    queryKey: ["llm-catalog", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/llm-settings/catalog");
      if (!data) throw new Error(`Failed to load catalog (${response.status})`);
      return data as Catalog;
    },
  });

  const settingsQuery = useQuery({
    queryKey: ["llm-settings", orgId],
    enabled: !!orgId,
    queryFn: async () => {
      const { data, response } = await api.GET("/llm-settings");
      if (!data) throw new Error(`Failed to load settings (${response.status})`);
      return data as LLMSettings;
    },
  });

  const save = useMutation({
    mutationFn: async (payload: Record<string, string>) => {
      const { data, error, response } = await api.PUT("/llm-settings", {
        body: payload as never,
      });
      if (!data) throw new Error(errorMessage(error, `Save failed (${response.status})`));
      return data;
    },
    onSuccess: () => {
      setKeyInputs({});
      setFeedback("Saved.");
      setTestResult(null);
      queryClient.invalidateQueries({ queryKey: ["llm-settings", orgId] });
    },
    onError: (saveError) => setFeedback(saveError.message),
  });

  const testConnection = useMutation({
    mutationFn: async (target: "chat" | "embedding") => {
      const { data, response } = await api.POST("/llm-settings/test", {
        body: { target },
      });
      if (!data) throw new Error(`Test failed (${response.status})`);
      return data as { ok: boolean; error?: string | null };
    },
    onSuccess: setTestResult,
    onError: (testError) => setTestResult({ ok: false, error: testError.message }),
  });

  const catalog = catalogQuery.data;
  const settings = settingsQuery.data;
  if (!catalog || !settings) {
    return <Skeleton className="h-48 w-full" />;
  }

  const effectiveChatProvider = chatProvider ?? settings.chat_provider;
  const providerInfo = catalog.chat_providers.find((p) => p.id === effectiveChatProvider);
  const effectiveChatModel =
    chatModel ??
    (chatProvider && chatProvider !== settings.chat_provider
      ? (providerInfo?.default_model ?? "")
      : settings.chat_model);
  const effectiveEmbedding = embeddingProvider ?? settings.embedding_provider;
  const embeddingInfo = catalog.embedding_providers.find((p) => p.id === effectiveEmbedding);

  // Only show the key fields the current selection actually uses.
  const relevantKeyFields = [
    ...new Set([providerInfo?.key_field, embeddingInfo?.key_field].filter(Boolean)),
  ] as string[];

  function handleSave() {
    setFeedback(null);
    const payload: Record<string, string> = {
      chat_provider: effectiveChatProvider,
      chat_model: effectiveChatModel,
      embedding_provider: effectiveEmbedding,
    };
    for (const [field, value] of Object.entries(keyInputs)) {
      payload[field] = value;
    }
    save.mutate(payload);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Provider</CardTitle>
        <CardDescription>
          Bring your own API key — your organization&apos;s usage is billed directly to your
          provider account. Keys are encrypted at rest and never displayed again.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Chat provider</Label>
            <Select
              value={effectiveChatProvider}
              onValueChange={(value) => {
                setChatProvider(value);
                setChatModel(null);
              }}
              disabled={!canEdit}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {catalog.chat_providers.map((provider) => (
                  <SelectItem key={provider.id} value={provider.id}>
                    {provider.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Model</Label>
            <Select
              value={effectiveChatModel}
              onValueChange={setChatModel}
              disabled={!canEdit}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(providerInfo?.models ?? []).map((model) => (
                  <SelectItem key={model} value={model}>
                    {model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Embeddings</Label>
            <Select
              value={effectiveEmbedding}
              onValueChange={setEmbeddingProvider}
              disabled={!canEdit}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {catalog.embedding_providers.map((provider) => (
                  <SelectItem key={provider.id} value={provider.id}>
                    {provider.label} ({provider.model})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {effectiveEmbedding !== settings.embedding_provider ? (
          <p className="text-xs text-amber-500">
            Changing the embedding provider requires re-uploading documents — existing
            vectors are not comparable across providers.
          </p>
        ) : null}

        <div className="grid max-w-xl gap-4">
          {relevantKeyFields.map((field) => (
            <KeyInput
              key={field}
              field={field}
              state={settings.keys[field]}
              value={keyInputs[field] ?? ""}
              disabled={!canEdit}
              onChange={(value) => setKeyInputs((prev) => ({ ...prev, [field]: value }))}
              onClear={() => setKeyInputs((prev) => ({ ...prev, [field]: "" }))}
            />
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={handleSave} disabled={!canEdit || save.isPending}>
            {save.isPending ? <Loader2Icon className="size-4 animate-spin" /> : null}
            Save
          </Button>
          <Button
            variant="outline"
            disabled={testConnection.isPending}
            onClick={() => testConnection.mutate("chat")}
          >
            Test chat
          </Button>
          <Button
            variant="outline"
            disabled={testConnection.isPending}
            onClick={() => testConnection.mutate("embedding")}
          >
            Test embeddings
          </Button>
          {testResult ? (
            testResult.ok ? (
              <span className="flex items-center gap-1 text-sm text-emerald-500">
                <CheckCircle2Icon className="size-4" /> Connection OK
              </span>
            ) : (
              <span
                className="flex items-center gap-1 text-sm text-destructive"
                title={testResult.error ?? undefined}
              >
                <XCircleIcon className="size-4" /> {testResult.error ?? "Failed"}
              </span>
            )
          ) : null}
        </div>
        {feedback ? <p className="text-sm text-muted-foreground">{feedback}</p> : null}
      </CardContent>
    </Card>
  );
}
