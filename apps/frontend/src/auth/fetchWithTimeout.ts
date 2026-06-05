const DEFAULT_TIMEOUT_MS = 15_000;

export type FetchWithTimeoutInit = RequestInit & { timeoutMs?: number };

/** `fetch` with abort after timeout — avoids infinite auth bootstrap spinner. */
export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: FetchWithTimeoutInit
): Promise<Response> {
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const { timeoutMs: _drop, ...rest } = init ?? {};
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    return await fetch(input, { ...rest, signal: ac.signal });
  } finally {
    clearTimeout(timer);
  }
}
