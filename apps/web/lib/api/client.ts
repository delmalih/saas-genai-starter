import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Auth token + active organization header are wired in SGS-010/SGS-013.
const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.status >= 500) {
      throw new ApiServerError(response.status, await response.clone().text());
    }
    return response;
  },
};

export class ApiServerError extends Error {
  constructor(
    public readonly status: number,
    body: string,
  ) {
    super(`API server error ${status}: ${body}`);
  }
}

export const api = createClient<paths>({ baseUrl });
api.use(errorMiddleware);
