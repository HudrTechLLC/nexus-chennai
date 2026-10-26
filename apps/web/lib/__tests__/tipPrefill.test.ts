/**
 * Unit tests for the /tip/new prefill (WS4-12): appeal -> form fields, and what the form sends.
 */

import { describe, expect, it } from "vitest";
import { validateTip } from "../tip";
import { appealSubject, prefillCategory, prefillCell, prefillWhen, tipFields, type PublicAppealFields } from "../tipPrefill";

// Shaped like a seeded appeal as public_appeal returns it (data/seed_appeals.py, PI-2026-CC4470).
const APPEAL: PublicAppealFields = {
  id: "PI-2026-CC4470", title: "Chain snatching in Guindy", category: "robbery", area: "Guindy",
  cell: "88618c4f49fffff", week: "2026-W40", time_window: "Morning",
  summary: "One morning in Guindy, a woman's gold chain was snatched. The rider escaped on a two-wheeler.",
};

describe("prefillCategory", () => {
  it("is vehicle_seen when the public text names a vehicle", () => {
    expect(prefillCategory(APPEAL)).toBe("vehicle_seen");
    expect(prefillCategory({ category: "vehicle_theft", title: "Theft in Adyar" })).toBe("vehicle_seen");
    expect(prefillCategory({ summary: "left in an autorickshaw" })).toBe("vehicle_seen");
    expect(prefillCategory({ summary: "drove off in a cab" })).toBe("vehicle_seen");
    expect(prefillCategory({ summary: "on a motorcycle" })).toBe("vehicle_seen");
    expect(prefillCategory({ category: "theft", title: "Car stolen in Kodambakkam" })).toBe("vehicle_seen"); // live PI-2026-45B216
  });
  it("is something_else otherwise, and never reads inside words", () => {
    expect(prefillCategory({ category: "burglary", title: "House break-in in Mylapore", summary: "Entered at night." })).toBe("something_else");
    expect(prefillCategory({ summary: "a cabinet was forced open" })).toBe("something_else");
    expect(prefillCategory({ summary: "a careful thief took cardamom" })).toBe("something_else");
    expect(prefillCategory({ title: "Phone snatched from a pedestrian in Mylapore" })).toBe("something_else");
    expect(prefillCategory({})).toBe("something_else");
  });
});

describe("prefillWhen", () => {
  it("matches the band whatever the case", () => {
    expect(prefillWhen("Morning")).toBe("Morning");
    expect(prefillWhen("night")).toBe("Night");
    expect(prefillWhen(" EVENING ")).toBe("Evening");
  });
  it("gives 'Not sure' for anything else", () => {
    expect(prefillWhen("dawn")).toBe("");
    expect(prefillWhen("")).toBe("");
    expect(prefillWhen(null)).toBe("");
  });
});

describe("prefillCell", () => {
  it("keeps only a resolution-8 cell the form accepts", () => {
    expect(prefillCell("88618c4f49fffff")).toBe("88618c4f49fffff");
    expect(prefillCell("89618c4f49fffff")).toBeNull();
    expect(prefillCell("not-a-cell")).toBeNull();
    expect(prefillCell(undefined)).toBeNull();
  });
});

describe("appealSubject", () => {
  it("prefills from public fields only", () => {
    expect(appealSubject(APPEAL)).toEqual({
      kind: "appeal", id: "PI-2026-CC4470", label: "Chain snatching in Guindy · Guindy · 2026-W40",
      category: "vehicle_seen", cell: "88618c4f49fffff", when: "Morning",
    });
  });
  it("gives a form that passes validation once the user writes something", () => {
    const s = appealSubject(APPEAL);
    expect(validateTip({ category: s.category, text: "I saw the rider", cell: s.cell, followUp: false, code: null, passphrase: null, appeal: s.id })).toBeNull();
  });
  it("drops a malformed cell instead of blocking step 1", () => {
    expect(appealSubject({ ...APPEAL, cell: "" }).cell).toBeNull();
  });
});

describe("tipFields", () => {
  const base = { category: "vehicle_seen", text: "I saw the rider", cell: "88618c4f49fffff", appeal: "PI-2026-CC4470", followUp: false, code: null, passphrase: null, pow: "p" };

  it("sends the appeal link while linked", () => {
    expect(Object.fromEntries(tipFields(base))).toEqual({
      pow: "p", category: "vehicle_seen", text: "I saw the rider", cell: "88618c4f49fffff", appeal: "PI-2026-CC4470",
    });
  });
  it("sends no appeal after the About line is removed", () => {
    const keys = tipFields({ ...base, appeal: null }).map(([k]) => k);
    expect(keys).not.toContain("appeal");
  });
  it("adds the follow-up fields only with a tip code", () => {
    expect(tipFields({ ...base, cell: null }).map(([k]) => k)).toEqual(["pow", "category", "text", "appeal"]);
    expect(Object.fromEntries(tipFields({ ...base, followUp: true, code: "8F3K2QWA", passphrase: "long enough" }))).toMatchObject({
      follow_up: "1", code: "8F3K2QWA", passphrase: "long enough",
    });
  });
});
