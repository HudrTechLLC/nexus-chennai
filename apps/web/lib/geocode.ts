/**
 * Place search for the map's "go to place" box (WS4-15). The server route `app/api/geocode` is a
 * thin wrapper around `createGeocoder`; the logic lives here so vitest can test it.
 *
 * Upstream is Photon (photon.komoot.io), an OpenStreetMap geocoder built for search-as-you-type.
 * Nominatim's usage policy forbids autocomplete, so it is not used. Results are OSM data (ODbL):
 * the UI must show "© OpenStreetMap contributors" wherever suggestions appear.
 *
 * Privacy: the query text is never logged or stored, apart from the in-memory cache key. This
 * module has no `console` calls (a test checks that).
 *
 * Limits, per server instance (each serverless instance has its own memory, so these are not global):
 *   - at most one upstream request per second: a call inside the window waits its turn;
 *     if the queue is already longer than the wait budget, the call is refused as `busy`;
 *   - an in-memory cache (TTL + size cap), so repeated queries never reach Photon;
 *   - a 3 s timeout per upstream request; a timeout or upstream error gives no suggestions.
 */

// =====================
// Types and constants
// =====================

export type Suggestion = { label: string; lat: number; lng: number };

/** `busy` = refused because too many requests are queued; the caller should retry shortly. */
export type GeocodeResult = { ok: true; suggestions: Suggestion[] } | { ok: false; reason: "busy" };

/** Chennai map bounds: west, south, east, north. Same as `cities/chennai/city.yaml` map.bounds. */
export const CHENNAI_BBOX: [number, number, number, number] = [80.05, 12.85, 80.33, 13.25];

export const PHOTON_URL = "https://photon.komoot.io/api/";
export const USER_AGENT = "NexusChennai/1.0 (+https://github.com/HudrTechLLC/nexus-chennai)";
export const MIN_QUERY = 3;
export const MAX_QUERY = 100;
export const MAX_SUGGESTIONS = 6;

type FetchFn = (url: string, init: RequestInit) => Promise<Response>;

export type GeocoderOptions = {
  fetchFn?: FetchFn;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  minIntervalMs?: number;
  timeoutMs?: number;
  maxWaitMs?: number;
  cacheTtlMs?: number;
  cacheMax?: number;
};

// =====================
// Helpers
// =====================

/** Trim, collapse spaces and cap the length. Returns null when shorter than MIN_QUERY. */
export function normaliseQuery(q: unknown): string | null {
  if (typeof q !== "string") return null;
  const s = q.replace(/\s+/g, " ").trim().slice(0, MAX_QUERY);
  return s.length >= MIN_QUERY ? s : null;
}

/** True when the point lies inside the bounds (west, south, east, north). */
export function inBox(lat: number, lng: number, box = CHENNAI_BBOX): boolean {
  const [w, s, e, n] = box;
  return lng >= w && lng <= e && lat >= s && lat <= n;
}

/** Short readable label from Photon properties: name, street, area, city; duplicates dropped. */
export function labelOf(p: Record<string, unknown>): string {
  const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string).trim() : "");
  const street = [str("housenumber"), str("street")].filter(Boolean).join(" ");
  const parts = [str("name"), street, str("locality"), str("district"), str("city")].filter(Boolean);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of parts) {
    const k = part.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      out.push(part);
    }
  }
  return out.slice(0, 4).join(", ");
}

/** Photon GeoJSON → suggestions inside Chennai. Photon coordinates are [lon, lat]. */
export function parsePhoton(body: unknown): Suggestion[] {
  const features = (body as { features?: unknown[] } | null)?.features;
  if (!Array.isArray(features)) return [];
  const out: Suggestion[] = [];
  const seen = new Set<string>();
  for (const f of features) {
    const g = (f as { geometry?: { coordinates?: unknown } }).geometry;
    const c = g?.coordinates;
    if (!Array.isArray(c) || typeof c[0] !== "number" || typeof c[1] !== "number") continue;
    const lng = c[0];
    const lat = c[1];
    if (!inBox(lat, lng)) continue;
    const label = labelOf(((f as { properties?: Record<string, unknown> }).properties) ?? {});
    if (!label || seen.has(label.toLowerCase())) continue;
    seen.add(label.toLowerCase());
    out.push({ label, lat: Math.round(lat * 1e6) / 1e6, lng: Math.round(lng * 1e6) / 1e6 });
    if (out.length >= MAX_SUGGESTIONS) break;
  }
  return out;
}

/** The upstream URL for a query, bounded to Chennai. */
export function photonUrl(q: string): string {
  const [w, s, e, n] = CHENNAI_BBOX;
  const u = new URL(PHOTON_URL);
  u.searchParams.set("q", q);
  u.searchParams.set("limit", String(MAX_SUGGESTIONS * 2)); // some may fall outside the box
  u.searchParams.set("lang", "en");
  u.searchParams.set("bbox", `${w},${s},${e},${n}`); // Photon order: minLon,minLat,maxLon,maxLat
  return u.toString();
}

// =====================
// Geocoder
// =====================

/** Creates a geocoder with its own throttle and cache. The route keeps one per server instance. */
export function createGeocoder(opts: GeocoderOptions = {}) {
  const fetchFn: FetchFn = opts.fetchFn ?? ((url, init) => fetch(url, init));
  const now = opts.now ?? (() => Date.now());
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const minInterval = opts.minIntervalMs ?? 1000;
  const timeoutMs = opts.timeoutMs ?? 3000;
  const maxWait = opts.maxWaitMs ?? 1000; // at most one request ahead in the queue
  const ttl = opts.cacheTtlMs ?? 10 * 60_000;
  const cacheMax = opts.cacheMax ?? 500;

  const cache = new Map<string, { at: number; value: Suggestion[] }>();
  let nextSlot = 0; // earliest time the next upstream request may start

  async function upstream(q: string): Promise<Suggestion[]> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetchFn(photonUrl(q), {
        headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
        signal: ctrl.signal,
        cache: "no-store",
      });
      if (!res.ok) return [];
      return parsePhoton(await res.json());
    } catch {
      return []; // timeout, network or bad JSON: no suggestions, nothing logged
    } finally {
      clearTimeout(timer);
    }
  }

  async function suggest(raw: unknown): Promise<GeocodeResult> {
    const q = normaliseQuery(raw);
    if (!q) return { ok: true, suggestions: [] };
    const key = q.toLowerCase();
    const hit = cache.get(key);
    if (hit && now() - hit.at < ttl) return { ok: true, suggestions: hit.value };

    const t = now();
    const wait = Math.max(0, nextSlot - t);
    if (wait > maxWait) return { ok: false, reason: "busy" };
    nextSlot = Math.max(t, nextSlot) + minInterval;
    if (wait > 0) await sleep(wait);

    const value = await upstream(q);
    if (cache.size >= cacheMax) cache.delete(cache.keys().next().value as string);
    cache.set(key, { at: now(), value });
    return { ok: true, suggestions: value };
  }

  return { suggest, cacheSize: () => cache.size };
}
