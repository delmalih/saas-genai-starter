import { getApiToken } from "./auth-token";
import { getActiveOrgId } from "../org-store";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; message_id: string }
  | { type: "error"; message: string };

// openapi-fetch doesn't expose response bodies as streams, so the SSE
// endpoint is consumed with a hand-rolled fetch reader.
export async function* streamChatMessage(
  conversationId: string,
  content: string,
): AsyncGenerator<ChatStreamEvent> {
  const token = await getApiToken();
  const orgId = getActiveOrgId();
  const response = await fetch(`${baseUrl}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok || !response.body) {
    let message = `Chat request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      message = body.error?.message ?? message;
    } catch {
      // keep the generic message
    }
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (dataLine) {
        yield JSON.parse(dataLine.slice("data: ".length)) as ChatStreamEvent;
      }
    }
  }
}
