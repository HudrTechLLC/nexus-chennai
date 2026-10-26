import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import {
  bbox, dossierAuthor, savingLabel, chunk, constellation, isoWeekStart, memberLonLat, memberSortKey, parseDossier, seriesHull, splitCitations,
  timeline, tokenSaving, weekSpan, type MemberPoint,
} from "../series";

const member = (id: string, extra: Partial<MemberPoint> = {}): MemberPoint => ({
  crime_id: id, station_id: "PS-A", station_name: "PS-A", category: "robbery", sub_type: null, fir_no: null,
  occurred_from: null, week: null, cell: null, lat: null, lon: null, full: false, ...extra,
});

describe("parseDossier", () => {
  it("reads the agreed shape", () => {
    const d = parseDossier({
      text: "# Series dossier", cited_ids: ["C1", 3, "C2"], chunks: 4, tokens_projected: 12000, tokens_actual: 4800,
      model: "nvidia/x", receipt_id: "ns_rcpt_1", run_id: "run_1", generated_at: "2026-10-26T10:00:00Z",
    });
    expect(d).toMatchObject({ text: "# Series dossier", cited_ids: ["C1", "C2"], chunks: 4, model: "nvidia/x", run_id: "run_1" });
    expect(tokenSaving(d!)).toBeCloseTo(0.6);
    expect(dossierAuthor(d!)).toEqual({ label: "nvidia/x", model: true });
  });

  it("labels a dossier with no model as the extractive fallback, never a model name", () => {
    const d = parseDossier({ text: "t", model: null, receipt_ids: ["r1", 2, "r2"], record_count: 140 })!;
    expect(dossierAuthor(d).model).toBe(false);
    expect(dossierAuthor(d).label).toMatch(/no model/);
    expect(d.receipt_ids).toEqual(["r1", "r2"]);
    expect(d.record_count).toBe(140);
  });

  it("is null without dossier text, so the page shows its empty state", () => {
    expect(parseDossier(null)).toBeNull();
    expect(parseDossier({})).toBeNull();
    expect(parseDossier({ text: "  " })).toBeNull();
    expect(parseDossier(["x"])).toBeNull();
    expect(parseDossier("text")).toBeNull();
  });

  it("tolerates chunks given as an array and missing token counts", () => {
    const d = parseDossier({ text: "t", chunks: [{}, {}, {}] })!;
    expect(d.chunks).toBe(3);
    expect(d.cited_ids).toEqual([]);
    expect(tokenSaving(d)).toBeNull();
  });
});

describe("splitCitations", () => {
  it("separates member crimes from other records and de-duplicates", () => {
    expect(splitCitations(["C1", "ST-9", "C1", "TIP-2"], ["C1", "C2"])).toEqual({ crimes: ["C1"], other: ["ST-9", "TIP-2"] });
  });
});

describe("timeline", () => {
  it("orders exact times and week-only members together, with day gaps between exact times", () => {
    const rows = timeline([
      member("C3", { occurred_from: "2026-04-10T10:00:00Z", full: true }),
      member("C1", { occurred_from: "2026-03-30T10:00:00Z", full: true }),
      member("C2", { week: "2026-W15" }), // Monday 6 Apr 2026
      member("C0"),
    ]);
    expect(rows.map((r) => r.crime_id)).toEqual(["C1", "C2", "C3", "C0"]);
    expect(rows[0].gapDays).toBeNull();
    expect(rows[2].gapDays).toBeNull(); // previous is week-only
    const two = timeline([member("A", { occurred_from: "2026-03-01T00:00:00Z" }), member("B", { occurred_from: "2026-03-03T12:00:00Z" })]);
    expect(two[1].gapDays).toBe(2.5);
  });

  it("finds the Monday of an ISO week", () => {
    expect(new Date(isoWeekStart("2026-W01")!).toISOString().slice(0, 10)).toBe("2025-12-29");
    expect(new Date(isoWeekStart("2026-W15")!).toISOString().slice(0, 10)).toBe("2026-04-06");
    expect(isoWeekStart("April")).toBeNull();
    expect(memberSortKey({ occurred_from: null, week: null })).toBe(Number.MAX_SAFE_INTEGER);
  });
});

describe("map helpers", () => {
  const cell = latLngToCell(13.0067, 80.2206, 8);

  it("uses the exact point when readable, else the H3 cell centre", () => {
    expect(memberLonLat({ lat: 13, lon: 80.2, cell })).toEqual({ p: [80.2, 13], exact: true });
    const c = memberLonLat({ lat: null, lon: null, cell })!;
    expect(c.exact).toBe(false);
    expect(c.p[0]).toBeCloseTo(80.2206, 2);
    expect(memberLonLat({ lat: null, lon: null, cell: "not-a-cell" })).toBeNull();
    expect(memberLonLat({ lat: null, lon: null, cell: null })).toBeNull();
  });

  it("builds a hull only from 3+ distinct points", () => {
    expect(seriesHull([[80, 13], [80, 13], [80.1, 13]])).toBeNull();
    const h = seriesHull([[80, 13], [80.1, 13], [80.05, 13.1], [80.05, 13.05]]);
    expect(h && h.length).toBeGreaterThanOrEqual(3);
  });

  it("computes a bounding box", () => {
    expect(bbox([])).toBeNull();
    expect(bbox([[80, 13], [80.2, 12.9]])).toEqual([80, 12.9, 80.2, 13]);
  });

  it("draws a constellation inside the box, one dot per cell, north up", () => {
    const north = latLngToCell(13.1, 80.2, 8);
    const south = latLngToCell(12.95, 80.2, 8);
    const { dots } = constellation([north, south, south], 120, 72, 8);
    expect(dots).toHaveLength(2);
    for (const d of dots) {
      expect(d.x).toBeGreaterThanOrEqual(0); expect(d.x).toBeLessThanOrEqual(120);
      expect(d.y).toBeGreaterThanOrEqual(0); expect(d.y).toBeLessThanOrEqual(72);
    }
    const [n, s] = dots;
    expect(n.y).toBeLessThan(s.y);
    expect(s.n).toBe(2);
    expect(constellation([]).dots).toEqual([]);
  });
});

describe("small helpers", () => {
  it("formats week spans", () => {
    expect(weekSpan(null, null)).toBe("—");
    expect(weekSpan("2026-W14", "2026-W14")).toBe("2026-W14");
    expect(weekSpan("2026-W14", "2026-W19")).toBe("2026-W14 → 2026-W19");
  });
  it("chunks ids", () => {
    expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    expect(chunk([], 2)).toEqual([]);
  });
});

describe("savingLabel", () => {
  it("shows a positive saving as fewer tokens", () => {
    expect(savingLabel({ chunks: 4, tokens_projected: 12000, tokens_actual: 4800 }).text).toBe("60% fewer tokens");
  });
  it("never shows a negative saving; explains a single chunk instead", () => {
    const l = savingLabel({ chunks: 1, tokens_projected: 1969, tokens_actual: 2369 }); // the live hero dossier
    expect(l.text).toBe("none");
    expect(l.hint).toMatch(/one chunk/);
    expect(savingLabel({ chunks: 3, tokens_projected: 100, tokens_actual: 100 }).hint).toMatch(/single read/);
  });
  it("is a dash when token counts are missing", () => {
    expect(savingLabel({ chunks: 2, tokens_projected: null, tokens_actual: 5 }).text).toBe("—");
  });
});
