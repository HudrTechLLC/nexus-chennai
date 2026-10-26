/**
 * Unit tests for the source-onboarding helpers (WS1-23): polling, start-form checks, the approve gate
 * (mirrors onboarding_decide), the changed-rows diff and the missing-table detection.
 */
import { describe, expect, it } from "vitest";
import {
  clip, dqCounts, isMissingTable, isTerminal, looksLikeText, mappingEdits, mappingIssues, MAX_UPLOAD_BYTES, ONBOARDING_STATUSES,
  rpcMessage, shouldPoll, stepIndex, STEPS, uploadPath, validateStart, type OnboardingField, type OnboardingMapping,
} from "../onboarding";

const F = (field: string, required: boolean, sort: number): OnboardingField => ({ field, label: field, required, kind: "text", sort });
const FIELDS = [F("fir_no", true, 1), F("occurred_from", true, 2), F("category", true, 5), F("lat", true, 8), F("lon", true, 9), F("narrative", false, 11)];
const M = (source_col: string, unified_field: string | null, extra: Partial<OnboardingMapping> = {}): OnboardingMapping => ({
  source_col, proposed_field: unified_field, unified_field, transform: "none", confidence: 0.9, reason: null, edited: false, ...extra,
});

describe("polling", () => {
  it("polls only while the worker owns the run", () => {
    expect(ONBOARDING_STATUSES.filter(shouldPoll)).toEqual(["uploaded", "profiling", "approved", "registering"]);
  });
  it("stops at proposed (a person decides) and at the end", () => {
    expect(shouldPoll("proposed")).toBe(false);
    expect(["registered", "rejected", "failed"].every((s) => isTerminal(s as never) && !shouldPoll(s as never))).toBe(true);
  });
  it("places stopped runs on the stepper", () => {
    expect(stepIndex("registered")).toBe(STEPS.length - 1);
    expect(stepIndex("rejected")).toBe(STEPS.indexOf("proposed"));
  });
});

describe("validateStart", () => {
  const ok = { sourceKey: "ps_new_station", label: "New station register", useSample: true };
  it("accepts the sample with a valid key and label", () => {
    expect(validateStart(ok)).toEqual({});
  });
  it("matches the migration's key rule", () => {
    expect(validateStart({ ...ok, sourceKey: "PS-New" }).source_key).toBeTruthy();
    expect(validateStart({ ...ok, sourceKey: "ab" }).source_key).toBeTruthy();
    expect(validateStart({ ...ok, sourceKey: "a".repeat(31) }).source_key).toBeTruthy();
  });
  it("needs a CSV of at most 2 MB when not using the sample", () => {
    const up = { ...ok, useSample: false };
    expect(validateStart({ ...up, file: null }).file).toMatch(/Choose/);
    expect(validateStart({ ...up, file: { name: "x.csv", size: MAX_UPLOAD_BYTES + 1 } }).file).toMatch(/2 MB/);
    expect(validateStart({ ...up, file: { name: "x.xlsx", size: 10 } }).file).toMatch(/\.csv/);
    expect(validateStart({ ...up, file: { name: "X.CSV", size: 10 } })).toEqual({});
  });
  it("rejects binary bytes and builds the bucket path the policy allows", () => {
    expect(looksLikeText(new TextEncoder().encode("a,b\n1,2\n"))).toBe(true);
    expect(looksLikeText(new Uint8Array([80, 75, 3, 4, 0, 0]))).toBe(false);
    expect(uploadPath("1b4e28ba-2fa1-11d2-883f-0016d3cca427")).toMatch(/^[0-9a-f-]{36}\/source\.csv$/);
  });
});

describe("mappingIssues (mirrors onboarding_decide)", () => {
  it("lists required fields not mapped, in sort order", () => {
    const rows = [M("FIR No", "fir_no"), M("Lat", "lat"), M("Brief", "narrative")];
    expect(mappingIssues(rows, FIELDS)).toEqual({ missing: ["occurred_from", "category", "lon"], duplicated: [] });
  });
  it("flags a field mapped twice and ignores null (ignored) columns", () => {
    const rows = [M("a", "fir_no"), M("b", "occurred_from"), M("c", "category"), M("d", "lat"), M("e", "lon"), M("f", "lat"), M("g", null)];
    expect(mappingIssues(rows, FIELDS)).toEqual({ missing: [], duplicated: ["lat"] });
  });
});

describe("mappingIssues: combined lat/long column", () => {
  it("counts a lat row with latlong_lat as lon too", () => {
    const rows = [M("a", "fir_no"), M("b", "occurred_from"), M("c", "category"), M("Lat/Long", "lat", { transform: "latlong_lat" })];
    expect(mappingIssues(rows, FIELDS)).toEqual({ missing: [], duplicated: [] });
  });
  it("still flags lon twice if a separate lon column is also mapped", () => {
    const rows = [M("a", "fir_no"), M("b", "occurred_from"), M("c", "category"), M("Lat/Long", "lat", { transform: "latlong_lat" }), M("Lon", "lon")];
    expect(mappingIssues(rows, FIELDS).duplicated).toEqual(["lon"]);
  });
  it("needs lon when lat is a plain column", () => {
    const rows = [M("a", "fir_no"), M("b", "occurred_from"), M("c", "category"), M("Lat", "lat")];
    expect(mappingIssues(rows, FIELDS).missing).toEqual(["lon"]);
  });
});

describe("mappingEdits", () => {
  it("sends only the rows that changed (the RPC marks every row it is sent as edited)", () => {
    const saved = [M("a", "fir_no"), M("b", "lat"), M("c", null)];
    const current = [
      { source_col: "a", unified_field: "fir_no", transform: "none" as const },
      { source_col: "b", unified_field: "lat", transform: "latlong_lat" as const },
      { source_col: "c", unified_field: "narrative", transform: "none" as const },
    ];
    expect(mappingEdits(saved, current).map((e) => e.source_col)).toEqual(["b", "c"]);
    expect(mappingEdits(saved, saved.map((m) => ({ source_col: m.source_col, unified_field: m.unified_field, transform: m.transform })))).toEqual([]);
  });
});

describe("display helpers", () => {
  it("clips raw values to one short line", () => {
    expect(clip("a\n  b   c")).toBe("a b c");
    expect(clip("x".repeat(100), 10)).toHaveLength(10);
    expect(clip({ a: 1 })).toBe('{"a":1}');
  });
  it("counts DQ findings by severity, most serious first", () => {
    expect(dqCounts([{ rule: "r1", severity: "warn", count: 3 }, { rule: "r2", severity: "error", count: 2 }, { rule: "r3", severity: "warn", count: 1 }]))
      .toEqual([{ severity: "error", findings: 1, rows: 2 }, { severity: "warn", findings: 2, rows: 4 }]);
    expect(dqCounts(null)).toEqual([]);
    expect(dqCounts([{ rule: "r0", severity: "warn", count: 0 }, { rule: "r1", severity: "info", count: 5 }]))
      .toEqual([{ severity: "info", findings: 1, rows: 5 }]);
  });
});

describe("errors", () => {
  it("treats a missing table as not set up (the page hides the section)", () => {
    expect(isMissingTable({ code: "42P01", message: 'relation "public.onboarding_runs" does not exist' })).toBe(true);
    expect(isMissingTable({ code: "PGRST205", message: "Could not find the table 'public.onboarding_runs' in the schema cache" })).toBe(true);
    expect(isMissingTable({ code: "42501", message: "permission denied" })).toBe(false);
    expect(isMissingTable(null)).toBe(false);
  });
  it("words the RPC errors a person can act on", () => {
    expect(rpcMessage({ code: "23505", message: "dup" })).toMatch(/already exists/);
    expect(rpcMessage({ code: "22023", message: "required fields not mapped: lat, lon" })).toBe("required fields not mapped: lat, lon");
  });
});
