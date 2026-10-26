import { createGeocoder } from "@/lib/geocode";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/geocode with body `{ "q": "<text>" }` → up to 6 place suggestions in Chennai:
 * `[{ label, lat, lng }]`.
 *
 * POST, not GET, so the typed place never sits in a URL or in platform request logs.
 * - Fewer than 3 characters, an upstream error or a 3 s timeout → `[]`.
 * - A body that isn't JSON → 400 `[]`.
 * - Too many queued requests on this instance → 429 `[]` with `Retry-After: 1` (retry once).
 * - Responses are never cached (`no-store`). The query text is never logged here or in lib/geocode.
 *
 * One geocoder per server instance, so the 1 request/s throttle and the cache are per instance.
 */
const geocoder = createGeocoder();

const HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" };

function json(body: unknown, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...HEADERS, ...extra } });
}

export async function POST(req: Request) {
  let q: unknown;
  try {
    q = ((await req.json()) as { q?: unknown } | null)?.q;
  } catch {
    return json([], 400);
  }
  const result = await geocoder.suggest(q);
  if (!result.ok) return json([], 429, { "Retry-After": "1" });
  return json(result.suggestions);
}
