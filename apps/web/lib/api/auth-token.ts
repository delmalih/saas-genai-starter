// Client-side JWT cache. Better Auth issues short-lived JWTs (signed for the
// API) from /api/auth/token based on the session cookie.

let cache: { token: string; expiresAt: number } | null = null;

function decodeExpiry(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1])) as { exp?: number };
    return (payload.exp ?? 0) * 1000;
  } catch {
    return 0;
  }
}

export async function getApiToken(): Promise<string | null> {
  if (cache && Date.now() < cache.expiresAt - 30_000) {
    return cache.token;
  }
  const response = await fetch("/api/auth/token");
  if (!response.ok) {
    return null;
  }
  const { token } = (await response.json()) as { token?: string };
  if (!token) {
    return null;
  }
  cache = { token, expiresAt: decodeExpiry(token) };
  return token;
}

export function clearApiTokenCache(): void {
  cache = null;
}
