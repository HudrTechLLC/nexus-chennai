/**
 * Unit tests for linking persons to a case (lib/persons.ts).
 */
import { describe, expect, it } from "vitest";
import { personLabel, toLinkPayload, validateLink, type LinkForm } from "../persons";

const f = (over: Partial<LinkForm> = {}): LinkForm => ({ role: "accused", personId: "", name: "", aliases: "", descriptors: {}, residenceWard: "", ...over });

describe("validateLink", () => {
  it("accepts a named accused, a described witness and an existing person", () => {
    expect(validateLink(f({ name: "Raju", aliases: "Pulsar Raju" }))).toBeNull();
    expect(validateLink(f({ role: "witness", descriptors: { gender: "F", age_band: "40-50" } }))).toBeNull();
    expect(validateLink(f({ role: "suspect", personId: "P-1" }))).toBeNull();
  });
  it("never names victims, witnesses or complainants (J5)", () => {
    expect(validateLink(f({ role: "victim", name: "Lakshmi" }))).toMatch(/described/);
    expect(validateLink(f({ role: "complainant", aliases: "x" }))).toMatch(/described/);
  });
  it("needs a name or a descriptor for a new person, and a numeric ward", () => {
    expect(validateLink(f())).toMatch(/at least one/);
    expect(validateLink(f({ name: "Raju", residenceWard: "ward 9" }))).toMatch(/number/);
  });
});

describe("toLinkPayload", () => {
  it("sends only person_id for an existing person", () => {
    expect(toLinkPayload("C1", f({ personId: "P-1", name: "ignored" }))).toEqual({ crime_id: "C1", role: "accused", person_id: "P-1" });
  });
  it("drops names for described roles and empty descriptors", () => {
    expect(toLinkPayload("C1", f({ role: "witness", name: "x", descriptors: { gender: "F", marks: " " } }))).toEqual({
      crime_id: "C1", role: "witness", descriptors: { gender: "F" },
    });
    expect(toLinkPayload("C1", f({ name: " Raju ", aliases: "A, B", residenceWard: "176" }))).toEqual({
      crime_id: "C1", role: "accused", descriptors: {}, name: "Raju", aliases: ["A", "B"], residence_ward: 176,
    });
  });
});

describe("personLabel", () => {
  it("shows names only for accused and suspects", () => {
    expect(personLabel("accused", { name: "Raju", aliases: ["Pulsar Raju"] })).toBe("Raju · aka Pulsar Raju");
    expect(personLabel("victim", { name: "Should Not Show", aliases: [] })).toBe("(identity masked)");
    expect(personLabel("suspect", { name: null, aliases: [] })).toBe("unnamed");
  });
});
