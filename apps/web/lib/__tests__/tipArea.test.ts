/**
 * Unit tests for the tip area sizes (WS4-15): which cells a tip may carry, moving between sizes,
 * zoom auto-step, and the browser place-search client.
 */

import { cellToParent, latLngToCell } from "h3-js";
import { describe, expect, it, vi } from "vitest";
import { fetchPlaces } from "../geocodeClient";
import { validateTip } from "../tip";
import { autoRes, DEFAULT_AREA_RES, isTipCell, resizeCell } from "../tipArea";

const P = { lat: 13.0067, lng: 80.2206 }; // Guindy
const R8 = latLngToCell(P.lat, P.lng, 8);
const R9 = latLngToCell(P.lat, P.lng, 9);
const R10 = latLngToCell(P.lat, P.lng, 10);

describe("isTipCell", () => {
  it("accepts H3 resolutions 8, 9 and 10", () => {
    expect([R8, R9, R10].map(isTipCell)).toEqual([true, true, true]);
    expect([R8[1], R9[1], R10[1]]).toEqual(["8", "9", "a"]);
  });
  it("refuses coarser or finer cells, points and junk", () => {
    expect(isTipCell(latLngToCell(P.lat, P.lng, 7))).toBe(false);
    expect(isTipCell(latLngToCell(P.lat, P.lng, 11))).toBe(false);
    expect(isTipCell("13.0067,80.2206")).toBe(false);
    expect(isTipCell("8a618c4f4ffffff".replace("f", "z"))).toBe(false);
    expect(isTipCell("")).toBe(false);
    expect(isTipCell(null)).toBe(false);
  });
  it("is what validateTip enforces", () => {
    const tip = { category: "vehicle_seen", text: "Red bike near the tea shop", followUp: false, code: null, passphrase: null, appeal: null };
    for (const cell of [R8, R9, R10, null]) expect(validateTip({ ...tip, cell })).toBeNull();
    expect(validateTip({ ...tip, cell: latLngToCell(P.lat, P.lng, 11) })).toMatch(/area/);
  });
});

describe("resizeCell", () => {
  it("defaults to Medium (r9)", () => expect(DEFAULT_AREA_RES).toBe(9));
  it("goes coarser via the parent", () => {
    expect(resizeCell(R10, 8, null)).toBe(R8);
    expect(resizeCell(R9, 8, P)).toBe(R8);
  });
  it("goes finer around the tapped point when it lies in the current cell", () => {
    expect(resizeCell(R8, 10, P)).toBe(R10);
    expect(resizeCell(R8, 9, P)).toBe(R9);
  });
  it("goes finer around the cell centre when there is no point (prefilled area)", () => {
    const fine = resizeCell(R8, 10, null)!;
    expect(isTipCell(fine) && cellToParent(fine, 8)).toBe(R8);
  });
  it("ignores a stale point outside the current cell", () => {
    const far = { lat: 13.08, lng: 80.27 };
    expect(cellToParent(resizeCell(R8, 10, far)!, 8)).toBe(R8);
  });
  it("keeps the cell at the same size, and starts from a point when there is no cell", () => {
    expect(resizeCell(R9, 9, P)).toBe(R9);
    expect(resizeCell(null, 10, P)).toBe(R10);
    expect(resizeCell(null, 9, null)).toBeNull();
  });
});

describe("autoRes", () => {
  it("steps finer when zooming in close, never coarser", () => {
    expect(autoRes(12, 8)).toBe(8);
    expect(autoRes(14, 8)).toBe(9);
    expect(autoRes(16, 8)).toBe(10);
    expect(autoRes(16, 9)).toBe(10);
    expect(autoRes(10, 10)).toBe(10);
  });
});

describe("fetchPlaces", () => {
  const ok = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
    new Response(JSON.stringify(body), { status, headers });

  it("POSTs the text in the body to our own route, never in the URL", async () => {
    const fetchFn = vi.fn(async () => ok([{ label: "Guindy", lat: 13.0, lng: 80.2 }]));
    expect(await fetchPlaces("  Guindy  station ", { fetchFn })).toEqual([{ label: "Guindy", lat: 13.0, lng: 80.2 }]);
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/geocode");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ q: "Guindy station" });
    expect(init.credentials).toBe("omit");
  });
  it("skips short input", async () => {
    const fetchFn = vi.fn();
    expect(await fetchPlaces(" ab ", { fetchFn })).toEqual([]);
    expect(fetchFn).not.toHaveBeenCalled();
  });
  it("retries once after a 429, then gives up quietly", async () => {
    const sleep = vi.fn(async () => {});
    const busy = vi.fn(async () => ok([], 429, { "Retry-After": "1" }));
    expect(await fetchPlaces("Adyar", { fetchFn: busy, sleep })).toEqual([]);
    expect(busy).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(1000);

    const once = vi.fn().mockResolvedValueOnce(ok([], 429)).mockResolvedValueOnce(ok([{ label: "Adyar", lat: 13, lng: 80.25 }]));
    expect(await fetchPlaces("Adyar", { fetchFn: once, sleep })).toHaveLength(1);
  });
  it("returns [] on errors and drops malformed items", async () => {
    expect(await fetchPlaces("Adyar", { fetchFn: async () => { throw new Error("offline"); } })).toEqual([]);
    expect(await fetchPlaces("Adyar", { fetchFn: async () => ok({ error: "x" }, 500) })).toEqual([]);
    expect(await fetchPlaces("Adyar", { fetchFn: async () => ok([{ label: "A", lat: "x", lng: 1 }, { label: "B", lat: 13, lng: 80 }]) }))
      .toEqual([{ label: "B", lat: 13, lng: 80 }]);
  });
  it("has no console calls (the typed place is never logged)", async () => {
    const src = (await import("node:fs")).readFileSync(new URL("../geocodeClient.ts", import.meta.url), "utf8");
    expect(src).not.toMatch(/console\./);
  });
});
