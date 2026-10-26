/**
 * Browser side of the place search on /tip/new (WS4-15). It only ever talks to our own route
 * (POST /api/geocode, #291), so the tipster's address never reaches a third party, and the typed text
 * goes in the body, never in a URL. Nothing here logs or stores the query.
 */

export type PlaceSuggestion = { label: string; lat: number; lng: number };

export const GEOCODE_DEBOUNCE_MS = 350;
export const GEOCODE_MIN_CHARS = 3;

type FetchFn = (url: string, init: RequestInit) => Promise<Response>;

function parse(body: unknown): PlaceSuggestion[] {
  if (!Array.isArray(body)) return [];
  return body.filter((s): s is PlaceSuggestion =>
    !!s && typeof s.label === "string" && Number.isFinite(s.lat) && Number.isFinite(s.lng)).slice(0, 6);
}

/**
 * Suggestions for `q`, or [] for short input and any failure. The route answers 429 when it is busy:
 * wait for Retry-After (about 1 s) and try once more; never show a busy answer as "no matches".
 */
export async function fetchPlaces(
  q: string,
  opts: { fetchFn?: FetchFn; sleep?: (ms: number) => Promise<void>; signal?: AbortSignal } = {},
): Promise<PlaceSuggestion[]> {
  const text = q.replace(/\s+/g, " ").trim();
  if (text.length < GEOCODE_MIN_CHARS) return [];
  const fetchFn: FetchFn = opts.fetchFn ?? ((url, init) => fetch(url, init));
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const init: RequestInit = {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: text }),
    credentials: "omit", referrerPolicy: "no-referrer", cache: "no-store", signal: opts.signal,
  };
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const r = await fetchFn("/api/geocode", init);
      if (r.status === 429 && attempt === 0) {
        const after = Number(r.headers.get("Retry-After"));
        await sleep(Number.isFinite(after) && after > 0 ? Math.min(after, 3) * 1000 : 1000);
        if (opts.signal?.aborted) return [];
        continue;
      }
      return r.ok ? parse(await r.json()) : [];
    } catch {
      return [];
    }
  }
  return [];
}
