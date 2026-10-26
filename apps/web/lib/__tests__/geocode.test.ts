/**
 * Unit tests for lib/geocode (WS4-15 server geocode route). fetch is mocked; nothing hits Photon.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  CHENNAI_BBOX,
  MAX_SUGGESTIONS,
  USER_AGENT,
  createGeocoder,
  labelOf,
  normaliseQuery,
  parsePhoton,
  photonUrl,
} from "../geocode";

// =====================
// Fixtures
// =====================

/** A Photon feature; coordinates are [lon, lat] like the real API. */
function feature(name: string, lon: number, lat: number, extra: Record<string, unknown> = {}) {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { name, ...extra } };
}

const ADYAR = feature("Adyar", 80.2574, 13.0012, { city: "Chennai" });
const BENGALURU = feature("MG Road", 77.6094, 12.9756, { city: "Bengaluru" });

function okFetch(features: unknown[]) {
  return vi.fn(async () => new Response(JSON.stringify({ type: "FeatureCollection", features }), { status: 200 }));
}

const SECRET_Q = "LB Road near the jewellers";

afterEach(() => vi.restoreAllMocks());

// =====================
// Helper tests
// =====================

describe("normaliseQuery", () => {
  it("trims, collapses spaces and caps at 100 characters", () => {
    expect(normaliseQuery("  Anna   Nagar ")).toBe("Anna Nagar");
    expect(normaliseQuery("x".repeat(300))!.length).toBe(100);
  });
  it("rejects fewer than 3 characters and non-strings", () => {
    expect(normaliseQuery("ad")).toBeNull();
    expect(normaliseQuery("   ab  ")).toBeNull();
    expect(normaliseQuery(null)).toBeNull();
    expect(normaliseQuery(42)).toBeNull();
  });
});

describe("photonUrl", () => {
  it("bounds the search to Chennai in Photon's minLon,minLat,maxLon,maxLat order", () => {
    const u = new URL(photonUrl("Adyar"));
    expect(u.hostname).toBe("photon.komoot.io");
    expect(u.searchParams.get("q")).toBe("Adyar");
    const [w, s, e, n] = CHENNAI_BBOX;
    expect(u.searchParams.get("bbox")).toBe(`${w},${s},${e},${n}`);
  });
});

describe("parsePhoton", () => {
  it("reads [lon, lat] correctly: a Chennai point comes back with lat ≈ 13 and lng ≈ 80", () => {
    const [s] = parsePhoton({ features: [ADYAR] });
    expect(s.lat).toBeCloseTo(13.0012, 4);
    expect(s.lng).toBeCloseTo(80.2574, 4);
    expect(s.label).toBe("Adyar, Chennai");
  });
  it("drops results outside the Chennai box, duplicates and malformed features", () => {
    const out = parsePhoton({ features: [ADYAR, BENGALURU, ADYAR, { geometry: null }, feature("", 80.2, 13.0)] });
    expect(out).toHaveLength(1);
  });
  it("returns at most 6 suggestions", () => {
    const many = Array.from({ length: 12 }, (_, i) => feature(`Place ${i}`, 80.2 + i * 0.001, 13.0));
    expect(parsePhoton({ features: many })).toHaveLength(MAX_SUGGESTIONS);
  });
  it("survives a non-GeoJSON body", () => {
    expect(parsePhoton(null)).toEqual([]);
    expect(parsePhoton({ features: "nope" })).toEqual([]);
  });
});

describe("labelOf", () => {
  it("joins name, street, area and city without repeats", () => {
    expect(labelOf({ name: "Velachery", district: "Velachery", city: "Chennai" })).toBe("Velachery, Chennai");
    expect(labelOf({ name: "Phoenix Mall", housenumber: "142", street: "Velachery Main Road", city: "Chennai" }))
      .toBe("Phoenix Mall, 142 Velachery Main Road, Chennai");
  });
});

// =====================
// Geocoder tests
// =====================

describe("createGeocoder", () => {
  it("returns [] for a short query without calling upstream", async () => {
    const fetchFn = okFetch([ADYAR]);
    const g = createGeocoder({ fetchFn });
    expect(await g.suggest("ad")).toEqual({ ok: true, suggestions: [] });
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("calls Photon with an identifying User-Agent and returns suggestions", async () => {
    const fetchFn = okFetch([ADYAR]);
    const g = createGeocoder({ fetchFn });
    const r = await g.suggest("Adyar");
    expect(r).toEqual({ ok: true, suggestions: [{ label: "Adyar, Chennai", lat: 13.0012, lng: 80.2574 }] });
    const init = (fetchFn.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)["User-Agent"]).toBe(USER_AGENT);
  });

  it("serves a repeated query from the cache, case-insensitively", async () => {
    const fetchFn = okFetch([ADYAR]);
    const g = createGeocoder({ fetchFn });
    await g.suggest("Adyar");
    await g.suggest("  adyar ");
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("expires cache entries after the TTL", async () => {
    let t = 0;
    const fetchFn = okFetch([ADYAR]);
    const g = createGeocoder({ fetchFn, now: () => t, sleep: async () => {}, cacheTtlMs: 1000 });
    await g.suggest("Adyar");
    t = 5000;
    await g.suggest("Adyar");
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("keeps the cache under its size cap", async () => {
    let t = 0;
    const g = createGeocoder({ fetchFn: okFetch([]), now: () => t, sleep: async () => {}, cacheMax: 3, minIntervalMs: 0 });
    for (const q of ["aaa", "bbb", "ccc", "ddd", "eee"]) {
      t += 1;
      await g.suggest(q);
    }
    expect(g.cacheSize()).toBe(3);
  });

  it("throttles upstream to one request per second: a second query waits for the window", async () => {
    const t = 1000;
    const sleep = vi.fn(async () => {});
    const g = createGeocoder({ fetchFn: okFetch([ADYAR]), now: () => t, sleep });
    await g.suggest("Adyar");
    const r = await g.suggest("Velachery");
    expect(r.ok).toBe(true);
    expect(sleep).toHaveBeenCalledWith(1000);
  });

  it("refuses as busy when the queue is longer than the wait budget", async () => {
    const t = 1000;
    const g = createGeocoder({ fetchFn: okFetch([ADYAR]), now: () => t, sleep: async () => {} });
    await g.suggest("aaa"); // takes the slot now
    await g.suggest("bbb"); // waits 1 s
    expect(await g.suggest("ccc")).toEqual({ ok: false, reason: "busy" }); // would wait 2 s
  });

  it("returns [] on an upstream error status", async () => {
    const g = createGeocoder({ fetchFn: vi.fn(async () => new Response("down", { status: 503 })) });
    expect(await g.suggest("Adyar")).toEqual({ ok: true, suggestions: [] });
  });

  it("returns [] when upstream exceeds the timeout", async () => {
    const hang: (u: string, init: RequestInit) => Promise<Response> = (_u, init) =>
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    const g = createGeocoder({ fetchFn: hang, timeoutMs: 20 });
    expect(await g.suggest("Adyar")).toEqual({ ok: true, suggestions: [] });
  });
});

// =====================
// Privacy: the query is never logged
// =====================

describe("query privacy", () => {
  it("never writes the query to the console on success, error or timeout", async () => {
    const spies = (["log", "info", "warn", "error", "debug", "trace"] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => {}),
    );
    const ok = createGeocoder({ fetchFn: okFetch([ADYAR]) });
    await ok.suggest(SECRET_Q);
    const bad = createGeocoder({ fetchFn: vi.fn(async () => { throw new Error(`boom ${SECRET_Q}`); }) });
    await bad.suggest(SECRET_Q);
    const slow = createGeocoder({
      fetchFn: (_u, init) => new Promise((_r, rej) => init.signal?.addEventListener("abort", () => rej(new Error("abort")))),
      timeoutMs: 10,
    });
    await slow.suggest(SECRET_Q);
    for (const s of spies) {
      for (const call of s.mock.calls) expect(JSON.stringify(call)).not.toContain("jewellers");
    }
  });

  it("has no console calls in the library or the route (structural)", () => {
    const root = path.resolve(__dirname, "../..");
    for (const f of ["lib/geocode.ts", "app/api/geocode/route.ts"]) {
      const src = fs.readFileSync(path.join(root, f), "utf8");
      expect(src, f).not.toMatch(/console\./);
    }
  });

  it("the route sends no-store and never caches", () => {
    const src = fs.readFileSync(path.resolve(__dirname, "../../app/api/geocode/route.ts"), "utf8");
    expect(src).toMatch(/"Cache-Control": "no-store"/);
    expect(src).toMatch(/dynamic = "force-dynamic"/);
  });
});
