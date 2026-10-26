/**
 * Unit tests for the public map theme (lib/publicMapTheme.ts): basemap style and outline colours follow the
 * visitor's light / dark preference.
 */
import { describe, expect, it } from "vitest";
import { MAP_INK, currentMapTheme, mapStyleUrl } from "../publicMapTheme";

describe("public map theme", () => {
  it("picks the dark basemap when the visitor prefers dark", () => {
    expect(currentMapTheme(() => ({ matches: true }))).toBe("dark");
    expect(currentMapTheme(() => ({ matches: false }))).toBe("light");
    expect(mapStyleUrl("dark")).toBe("/map/dark.json");
    expect(mapStyleUrl("light")).toBe("/map/light.json");
  });
  it("falls back to light without a browser (server render, tests)", () => {
    expect(currentMapTheme()).toBe("light");
  });
  it("uses the site's own signal and ink colours for each theme", () => {
    expect(MAP_INK.light.signal).toBe("#0e7c86");
    expect(MAP_INK.dark.signal).toBe("#45c2cc"); // --signal in dark mode (globals.css)
    expect(MAP_INK.dark.selected).toBe("#e4eaf1"); // --ink in dark mode
  });
});
