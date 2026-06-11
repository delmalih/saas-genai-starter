import createClient, { type Middleware } from "openapi-fetch";
import { getApiToken } from "./auth-token";
import { getActiveOrgId } from "../org-store";
import type { paths } from "./schema";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiServerError extends Error {
  constructor(
    public readonly status: number,
    body: string,
  ) {
    super(`API server error ${status}: ${body}`);
  }
}

// Browser only: attach the session JWT and the active organization.
// Server components calling public endpoints (e.g. /health) skip this.
const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (typeof window === "undefined") {
      return request;
    }
    const token = await getApiToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    const orgId = getActiveOrgId();
    if (orgId && !request.headers.has("X-Org-Id")) {
      request.headers.set("X-Org-Id", orgId);
    }
    return request;
  },
};

const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.status >= 500) {
      throw new ApiServerError(response.status, await response.clone().text());
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl });
api.use(authMiddleware);
api.use(errorMiddleware);

export interface ApiErrorBody {
  error?: { code?: string; message?: string };
}

export function errorMessage(body: unknown, fallback: string): string {
  return (body as ApiErrorBody)?.error?.message ?? fallback;
}
