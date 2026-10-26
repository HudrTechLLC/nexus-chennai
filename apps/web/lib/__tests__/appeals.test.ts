import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { caseLeakKind, caseTerms, isCrimeId, leakKind, parseLookingFor, tipCounts, validateAppeal } from "../appeals";

// The same fixture pytest and the SQL check use, so the three leak lists cannot drift apart.
const fixture = JSON.parse(
  readFileSync(resolve(__dirname, "../../../../tests/agents/appeal_leaks.json"), "utf-8"),
) as {
  leaky: { text: string; kind: string }[];
  clean: string[];
  case_leaks: {
    persons: { name: string | null; aliases: string[] }[];
    address: string;
    more_addresses: { address: string; leaky: string[]; clean: string[] }[];
    leaky: { text: string; kind: string }[];
    clean: string[];
  };
};

describe("leakKind (shared fixture)", () => {
  it("catches every leaky text with the right kind", () => {
    for (const c of fixture.leaky) expect(leakKind(c.text)).toBe(c.kind);
  });
  it("passes every clean text, including the spec's CCTV time window", () => {
    for (const t of fixture.clean) expect(leakKind(t)).toBeNull();
  });
});

describe("validateAppeal", () => {
  const ok = { title: "Chain snatching by two riders", summary: "A gold chain was snatched.", looking_for: ["Red motorcycle"] };
  it("accepts a clean appeal", () => expect(validateAppeal(ok)).toBeNull());
  it("rejects empty or leaky fields", () => {
    expect(validateAppeal({ ...ok, title: " " })).toMatch(/title/);
    expect(validateAppeal({ ...ok, summary: "Bike TN 09 BX 4471" })).toMatch(/plate/);
    expect(validateAppeal({ ...ok, looking_for: ["FIR 1182/2026"] })).toMatch(/FIR number/);
  });
});

describe("helpers", () => {
  it("parses looking-for lines", () => {
    expect(parseLookingFor(" a \n\nb\r\nc\nd\ne")).toEqual(["a", "b", "c", "d"]);
  });
  it("validates crime ids", () => {
    expect(isCrimeId("CHN-AD-2026-001182")).toBe(true);
    expect(isCrimeId("CHN-AD-2026-001182,x")).toBe(false);
    expect(isCrimeId("")).toBe(false);
  });
});

describe("tipCounts", () => {
  it("counts tips per appeal and ignores general tips", () => {
    const m = tipCounts([{ public_incident_id: "PI-1" }, { public_incident_id: "PI-1" }, { public_incident_id: null }, { public_incident_id: "PI-2" }]);
    expect(Object.fromEntries(m)).toEqual({ "PI-1": 2, "PI-2": 1 });
  });
});

describe("per-case leaks (shared fixture case_leaks, 0007_08)", () => {
  const cl = fixture.case_leaks;
  const terms = caseTerms(cl.persons, cl.address);
  it("catches names, aliases and the case address with the right kind", () => {
    for (const c of cl.leaky) expect([c.text, caseLeakKind(c.text, terms)]).toEqual([c.text, c.kind]);
  });
  it("passes clean texts: whole words only, short aliases ignored, the motorcycle model is not a name", () => {
    for (const t of cl.clean) expect([t, caseLeakKind(t, terms)]).toEqual([t, null]);
  });
  it("blocks landmarks and door addresses, never a plain road or locality", () => {
    for (const a of cl.more_addresses) {
      const t = caseTerms([], a.address);
      for (const x of a.leaky) expect([x, caseLeakKind(x, t)]).toEqual([x, "place from the case address"]);
      for (const x of a.clean) expect([x, caseLeakKind(x, t)]).toEqual([x, null]);
    }
  });
  it("blocks a publish that names someone in the case", () => {
    const ok = { title: "Chain snatching", summary: "Karthik was seen nearby.", looking_for: [] };
    expect(validateAppeal(ok, terms)).toMatch(/person name from the case/);
    expect(validateAppeal(ok)).toBeNull(); // without the case's terms only the pattern list applies
  });
});

describe("area label (0007_09)", () => {
  const ok = { title: "Mobile snatching", summary: "A phone was snatched.", looking_for: [], area_label: "Adyar" };
  it("is required when sent, short, and leak-checked like the other fields", () => {
    expect(validateAppeal(ok)).toBeNull();
    expect(validateAppeal({ ...ok, area_label: " " })).toMatch(/area/);
    expect(validateAppeal({ ...ok, area_label: "x".repeat(61) })).toMatch(/60/);
    const terms = caseTerms([], "near VHS Hospital, Adyar");
    expect(validateAppeal({ ...ok, area_label: "Adyar (near VHS Hospital, Adyar area)" }, terms)).toMatch(/area contains a place from the case address/);
  });
});
