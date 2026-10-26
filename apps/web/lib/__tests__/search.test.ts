/**
 * Unit tests for console search parsing (lib/search.ts).
 */
import { describe, expect, it } from "vitest";
import { aliasVariants, classifyQuery, evidenceFilter, hasCriteria, parseSearch, personFilter, searchWords } from "../search";

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
    expect(p.facets).toMatchObject({ station: "PS-ADYAR-J2", category: "robbery", status: null, from: "2026-10-01", to: null });
  });
  it("needs a query or a facet", () => {
    expect(hasCriteria(parseSearch({}))).toBe(false);
    expect(hasCriteria(parseSearch({ category: "theft" }))).toBe(true);
  });
});

describe("SRCH-03 facets and similar mode", () => {
  it("parses weapon, zone, MO tag, time band and linked", () => {
    const p = parseSearch({ weapon: "Knife", zone: "Adyar", mo: "two wheeler from behind", tod: "night", linked: "unlinked" });
    expect(p.facets).toMatchObject({ weapon: "knife", zone: "Adyar", mo: "two_wheeler_from_behind", tod: "night", linked: "unlinked" });
    expect(hasCriteria(p)).toBe(true);
  });
  it("drops malformed facet values", () => {
    const p = parseSearch({ weapon: "knife%", zone: "Adyar;drop", mo: "x", tod: "noon", linked: "maybe" });
    expect(p.facets).toMatchObject({ weapon: null, zone: null, mo: null, tod: null, linked: null });
  });
  it("accepts a case id for similar mode only", () => {
    expect(parseSearch({ similar: "chn-ad-2026-001231" }).similar).toBe("CHN-AD-2026-001231");
    expect(parseSearch({ similar: "1231" }).similar).toBeNull();
    expect(hasCriteria(parseSearch({ similar: "CHN-AD-2026-001231" }))).toBe(true);
  });
});

describe("alias search (SRCH-05)", () => {
  it("offers the phrase and each word in lower, Title and UPPER case", () => {
    const v = aliasVariants(["pulsar", "raju"]);
    expect(v).toEqual(expect.arrayContaining(["pulsar raju", "Pulsar Raju", "PULSAR RAJU", "raju", "Raju", "RAJU", "Pulsar"]));
  });
  it("strips anything that could break the array literal", () => {
    expect(aliasVariants(['a"}', "x"])).toEqual([]);
    expect(aliasVariants(['sa"thish}'])).toEqual(["sathish", "Sathish", "SATHISH"]);
  });
  it("matches a name fragment or an exact alias", () => {
    expect(personFilter(["sathish"])).toBe('name.ilike.%sathish%,aliases.ov.{"sathish","Sathish","SATHISH"}');
    expect(personFilter([])).toBe("");
  });
});

describe("evidence search (SRCH-01)", () => {
  it("matches a camera id fragment, and an evidence kind a word names", () => {
    expect(evidenceFilter(["cctv"])).toBe("camera_id.ilike.%cctv%,kind.in.(cctv_still,cctv_clip)");
    expect(evidenceFilter(["cam-17"])).toBe("camera_id.ilike.%cam-17%");
    expect(evidenceFilter(["photo"])).toBe("camera_id.ilike.%photo%,kind.in.(photo)");
  });
  it("drops characters that could change the filter", () => {
    expect(evidenceFilter(["a,b)", "x"])).toBe("camera_id.ilike.%ab%");
  });
});
