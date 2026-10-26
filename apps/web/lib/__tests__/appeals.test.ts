import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { isCrimeId, leakKind, parseLookingFor, tipCounts, validateAppeal } from "../appeals";

// The same fixture pytest and the SQL check use, so the three leak lists cannot drift apart.
const fixture = JSON.parse(
  readFileSync(resolve(__dirname, "../../../../tests/agents/appeal_leaks.json"), "utf-8"),
) as { leaky: { text: string; kind: string }[]; clean: string[] };

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
