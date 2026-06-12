import { getApiToken } from "./auth-token";
import { getActiveOrgId } from "../org-store";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Multipart upload — openapi-fetch is JSON-oriented, so this goes manual.
export async function uploadDocument(file: File): Promise<void> {
  const token = await getApiToken();
  const orgId = getActiveOrgId();
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${baseUrl}/documents`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
    },
    body,
  });
  if (!response.ok) {
    let message = `Upload failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      message = payload.error?.message ?? message;
    } catch {
      // keep the generic message
    }
    throw new Error(message);
  }
}
