/**
 * Unit tests for the console Data sources page helpers (WS3-27): numbers only from the DB, honest fallbacks.
 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { accessForPath, navFor } from "../roles";
import {
  DATA_SOURCES, MIRROR_TABLES, SOURCE_TYPES, dqFor, sourceNumber, unifiedDq, zetarisCounts, type StatusRow,
} from "../dataSources";

const src = (id: string) => DATA_SOURCES.find((s) => s.id === id)!;
const row = (component: string, detail: unknown, checked_at = "2026-10-26T14:54:51+00:00"): StatusRow =>
  ({ component, state: "live", detail, checked_at });

describe("registry", () => {
  it("has unique ids and at least six source types", () => {
    expect(new Set(DATA_SOURCES.map((s) => s.id)).size).toBe(DATA_SOURCES.length);
    expect(SOURCE_TYPES.length).toBeGreaterThanOrEqual(6);
  });
  it("names which unified view each FIR source feeds", () => {
    for (const id of ["sb.crimes", "s3csv.cctns", "s3pq.archive"]) expect(src(id).feeds).toContain("v_crime_unified");
    expect(src("sb.crimes").feeds).toContain("case_bundle_v");
    expect(src("sb.evidence_media").feeds).toContain("case_bundle_v");
  });
  it("covers the ANPR, CCTV, 112 and REST sources", () => {
    for (const id of ["s3pq.anpr_reads", "s3csv.cctv_cameras", "s3pq.calls", "nexus_feeds.rest_news", "nexus_feeds.rest_social", "nexus_feeds.rest_weather"])
      expect(src(id)).toBeDefined();
  });
  it("hard-codes no counts and no city (numbers come from the DB; D-004)", () => {
    const code = readFileSync(new URL("../dataSources.ts", import.meta.url), "utf8");
    expect(code).not.toMatch(/\b\d{4,}\b|\b\d{1,3},\d{3}\b/); // no row counts such as 14040 or 2,500
    expect(code).not.toMatch(/Chennai/i);
    expect(code).not.toMatch(/auto-?discover/i);
    const page = readFileSync(new URL("../../app/console/(app)/system/sources/page.tsx", import.meta.url), "utf8");
    expect(page).not.toMatch(/\b(14,?040|2,?500|19,?540|70)\b/);
    expect(page).not.toMatch(/auto-?discover/i);
  });
  it("counts each Supabase table once", () => {
    expect(new Set(MIRROR_TABLES).size).toBe(MIRROR_TABLES.length);
    expect(MIRROR_TABLES).toContain("crimes");
  });
});

describe("sourceNumber", () => {
  const mirrors = { crimes: 14040, map_call_cells: 119971 };

  it("prefers the Zetaris count, with its time", () => {
    expect(sourceNumber(src("sb.crimes"), { "sb.crimes": 14040 }, "T", mirrors)).toEqual({ kind: "zetaris", n: 14040, asOf: "T" });
  });
  it("falls back to the Supabase table, labelled when it is only a projection", () => {
    expect(sourceNumber(src("sb.crimes"), {}, null, mirrors)).toEqual({ kind: "mirror", n: 14040, table: "crimes", note: undefined });
    expect(sourceNumber(src("s3pq.calls"), {}, null, mirrors)).toMatchObject({ kind: "mirror", table: "map_call_cells", note: expect.stringMatching(/not calls/) });
  });
  it("says 'live only' instead of inventing a number", () => {
    expect(sourceNumber(src("s3csv.cctns"), {}, null, mirrors)).toEqual({ kind: "live-only" });
    expect(sourceNumber(src("sb.crimes"), {}, null, { crimes: null })).toEqual({ kind: "live-only" });
    expect(sourceNumber(src("nexus_feeds.rest_news"), {}, null, mirrors)).toEqual({ kind: "live-only" });
  });
});

describe("system_status rows", () => {
  it("reads per-source counts from 'zetaris:sources', dropping unknown keys and junk", () => {
    expect(zetarisCounts(row("zetaris:sources", { counts: { "s3csv.cctns": 3000, "x.y": 5, "s3pq.archive": "lots", "sb.crimes": -1 } })))
      .toEqual({ "s3csv.cctns": 3000 });
    expect(zetarisCounts(undefined)).toEqual({});
    expect(zetarisCounts(row("zetaris:sources", null))).toEqual({});
  });
  it("assigns DQ counts to their sources", () => {
    const dq = row("zetaris:dq", { duplicate_fir: 30, bad_geo: 5, time_inconsistent: 5, unmapped_section: 20, orphan_evidence: 0, tip_without_incident: 36, stale_camera: 134, total: 230 });
    // crime-level rules run over v_crime_unified (current + legacy together), so no single source owns them
    expect(unifiedDq(dq)).toEqual({ duplicate_fir: 30, bad_geo: 5, time_inconsistent: 5, unmapped_section: 20 });
    expect(dqFor(src("sb.crimes"), dq)).toEqual({});
    expect(dqFor(src("sb.evidence_media"), dq)).toEqual({ orphan_evidence: 0 });
    expect(dqFor(src("sb.tips_v"), dq)).toEqual({ tip_without_incident: 36 });
    expect(dqFor(src("s3csv.cctv_cameras"), dq)).toEqual({ stale_camera: 134 });
    expect(unifiedDq(undefined)).toEqual({});
    expect(dqFor(src("nexus_feeds.rest_news"), dq)).toEqual({});
    expect(dqFor(src("sb.crimes"), undefined)).toEqual({});
  });
});

describe("navigation", () => {
  it("is an admin page in the Manage menu", () => {
    expect(accessForPath("/console/system/sources")).toBe("admin");
    expect(navFor("admin").map((n) => n.href)).toContain("/console/system/sources");
    expect(navFor("supervisor").map((n) => n.href)).not.toContain("/console/system/sources");
  });
});
