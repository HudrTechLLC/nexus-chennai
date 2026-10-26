/**
 * Unit tests for the public crime-card helpers (lib/publicCards.ts): URL map state, labels and links.
 */
import { describe, expect, it } from "vitest";
import {
  STATUS_LABEL, cardTitle, crimeHref, isPublicId, mapHref, mapStateQuery, parseMapState, weekLabel, type CrimeCard,
} from "../publicCards";

const HEX = "8861892b3ffffff";

describe("parseMapState", () => {
  it("reads days, type, hex and view from the URL", () => {
    expect(parseMapState({ days: "90", type: "robbery", hex: HEX, at: "80.25651,13.00123,13.5" })).toEqual({
      days: 90, type: "robbery", hex: HEX, at: [80.2565, 13.0012, 13.5],
    });
  });
  it("falls back to safe defaults and drops anything malformed", () => {
    expect(parseMapState({})).toEqual({ days: 30, type: null, hex: null, at: null });
    expect(parseMapState({ days: "45", type: "Robbery'; drop", hex: "88zz", at: "1,2,3" })).toEqual({
      days: 30, type: null, hex: null, at: null,
    });
    expect(parseMapState({ at: "80.2,13.0" })).toEqual({ days: 30, type: null, hex: null, at: null });
    expect(parseMapState({ at: "80.2,13.0,40" }).at).toBeNull(); // zoom out of range
  });
  it("treats ?cell= (appeal pages' crime-map link) as the selected hex", () => {
    expect(parseMapState({ cell: HEX }).hex).toBe(HEX);
    expect(parseMapState({ cell: HEX.toUpperCase() }).hex).toBe(HEX);
    expect(parseMapState({ hex: HEX, cell: "8861892b7ffffff" }).hex).toBe(HEX);
    expect(mapStateQuery(parseMapState({ cell: HEX }))).toBe(`hex=${HEX}`);
  });
  it("accepts URLSearchParams too", () => {
    expect(parseMapState(new URLSearchParams(`days=7&hex=${HEX}`))).toMatchObject({ days: 7, hex: HEX });
  });
});

describe("mapStateQuery / mapHref / crimeHref", () => {
  const state = { days: 90 as const, type: "robbery", hex: HEX, at: [80.2565, 13.0012, 13.5] as [number, number, number] };
  it("round-trips through the URL", () => {
    expect(parseMapState(new URLSearchParams(mapStateQuery(state)))).toEqual(state);
  });
  it("omits defaults and empty values", () => {
    expect(mapStateQuery({ days: 30, type: null, hex: null, at: null })).toBe("");
    expect(mapHref({ days: 30, type: null, hex: HEX, at: null })).toBe(`/map?hex=${HEX}`);
  });
  it("links a card to its detail page, carrying the map state for Back to map", () => {
    expect(crimeHref("PC-3F9A0C12B7E4", state)).toBe(`/map/crime/PC-3F9A0C12B7E4?${mapStateQuery(state)}`);
    expect(mapHref(state)).toBe(`/map?${mapStateQuery(state)}`);
  });
});

describe("labels", () => {
  const card: CrimeCard = {
    public_id: "PC-3F9A0C12B7E4", category: "robbery", sub_type: "chain_snatching", week: "2026-W42",
    time_window: "evening", cell: HEX, area: "Adyar", status: "charge-sheeted", in_pattern: true,
    mo_summary: null, appeals: [],
  };
  it("names the crime in plain words", () => {
    expect(cardTitle(card)).toBe("Robbery · Chain snatching");
    expect(cardTitle({ ...card, sub_type: null })).toBe("Robbery");
    expect(cardTitle({ ...card, category: "crimes_against_women", sub_type: "crimes_against_women" })).toBe("Crimes against women");
  });
  it("shows a filed charge sheet without names or dates (chief)", () => {
    expect(STATUS_LABEL["charge-sheeted"]).toBe("Charge sheet filed");
    expect(STATUS_LABEL.open).toBe("Open");
    expect(STATUS_LABEL.closed).toBe("Closed");
  });
  it("says the ISO week", () => {
    expect(weekLabel("2026-W42")).toBe("Week 42, 2026");
    expect(weekLabel("2026-W07")).toBe("Week 7, 2026");
    expect(weekLabel("junk")).toBe("junk");
  });
  it("recognises public ids only", () => {
    expect(isPublicId("PC-3F9A0C12B7E4")).toBe(true);
    expect(isPublicId("CHN-AD-2026-001182")).toBe(false);
    expect(isPublicId("pc-3f9a0c12b7e4")).toBe(false);
  });
});
