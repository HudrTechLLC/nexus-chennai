/**
 * Unit tests for console search parsing (lib/search.ts).
 */
import { describe, expect, it } from "vitest";
import { classifyQuery, hasCriteria, parseSearch, searchWords } from "../search";

describe("classifyQuery", () => {
  it("recognises case ids", () => {
    expect(classifyQuery("chn-ad-2026-001182")).toEqual({ kind: "crime_id", value: "CHN-AD-2026-001182" });
  });
  it("recognises FIR numbers", () => {
    expect(classifyQuery("1182/2026")).toEqual({ kind: "fir", value: "1182/2026" });
    expect(classifyQuery("FIR no. 877")).toEqual({ kind: "fir", value: "877" });
  });
  it("recognises plate fragments", () => {
    expect(classifyQuery("TN 09 ?? 4471")).toEqual({ kind: "plate", value: "TN09??4471" });
    expect(classifyQuery("tn09ab")).toEqual({ kind: "plate", value: "TN09AB" });
    expect(classifyQuery("4471")).toEqual({ kind: "plate", value: "4471" });
  });
  it("treats everything else as words", () => {
    expect(classifyQuery("red pulsar chain snatching").kind).toBe("text");
    expect(classifyQuery("helmet").kind).toBe("text");
    expect(classifyQuery("   ").kind).toBe("empty");
  });
});

describe("searchWords", () => {
  it("drops LIKE wildcards, short words and duplicates; caps at 6", () => {
    expect(searchWords("Red red % pulsar_ a, (chain)")).toEqual(["red", "pulsar", "chain"]);
    expect(searchWords("a1 b2 c3 d4 e5 f6 g7 h8")).toHaveLength(6);
  });
});

describe("parseSearch", () => {
  it("keeps valid facets and words", () => {
    const p = parseSearch({ q: "black helmet", station: "PS-ADYAR-J2", category: "robbery", from: "2026-10-01", status: "nope" });
    expect(p.kind).toBe("text");
    expect(p.words).toEqual(["black", "helmet"]);
    expect(p.facets).toEqual({ station: "PS-ADYAR-J2", category: "robbery", status: null, from: "2026-10-01", to: null });
  });
  it("needs a query or a facet", () => {
    expect(hasCriteria(parseSearch({}))).toBe(false);
    expect(hasCriteria(parseSearch({ category: "theft" }))).toBe(true);
  });
});
