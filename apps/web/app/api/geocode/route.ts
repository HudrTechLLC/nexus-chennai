import { createGeocoder } from "@/lib/geocode";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/geocode?q=<text> → up to 6 place suggestions in Chennai: `[{ label, lat, lng }]`.
 *
 * - Fewer than 3 characters, an upstream error or a 3 s timeout → `[]`.
 * - Too many queued requests on this instance → 429 with `Retry-After: 1` (retry once).
 * - Responses are never cached (`no-store`). The query text is never logged here or in lib/geocode.
 *
 * One geocoder per server instance, so the 1 request/s throttle and the cache are per instance.
 */
const geocoder = createGeocoder();

const HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" };

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get("q");
  const result = await geocoder.suggest(q);
  if (!result.ok) {
    return new Response(JSON.stringify([]), { status: 429, headers: { ...HEADERS, "Retry-After": "1" } });
  }
  return new Response(JSON.stringify(result.suggestions), { status: 200, headers: HEADERS });
}
