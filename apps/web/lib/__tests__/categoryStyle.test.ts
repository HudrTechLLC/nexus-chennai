/**
 * Unit tests for lib/categoryStyle.ts: every category has an icon and readable colours in both themes, and the
 * category hues stay clear of the map's density ramp.
 */
import { describe, expect, it } from "vitest";
import { CATEGORY_STYLE, FALLBACK_STYLE, categoryStyle, categoryVars, contrast } from "../categoryStyle";
import { DENSITY_RAMP, densityFill, densityGradient } from "../publicMapTheme";

const CATEGORIES = ["robbery", "theft", "house_break", "hurt", "cheating", "crimes_against_women", "homicide", "kidnapping"];

describe("category style", () => {
  it("covers every crime category, with a fallback for unknown keys", () => {
    for (const c of CATEGORIES) expect(CATEGORY_STYLE[c], c).toBeDefined();
    expect(categoryStyle("arson")).toBe(FALLBACK_STYLE);
    expect(categoryStyle(null)).toBe(FALLBACK_STYLE);
    expect(categoryStyle("")).toBe(FALLBACK_STYLE);
  });

  it("meets WCAG AA (4.5:1) for the label on its own background, light and dark", () => {
    for (const s of [...Object.values(CATEGORY_STYLE), FALLBACK_STYLE]) {
      expect(contrast(s.light.fg, s.light.bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(s.dark.fg, s.dark.bg)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps the card stripe (a non-text mark in the fg colour) at 3:1 or more against the card surface", () => {
    const surface = { light: "#ffffff", dark: "#111b26" }; // --surface in globals.css, light and dark
    for (const s of [...Object.values(CATEGORY_STYLE), FALLBACK_STYLE]) {
      expect(contrast(s.light.fg, surface.light)).toBeGreaterThanOrEqual(3);
      expect(contrast(s.dark.fg, surface.dark)).toBeGreaterThanOrEqual(3);
    }
  });

  it("gives each category its own colour, none of them a density-ramp colour", () => {
    const fgs = Object.values(CATEGORY_STYLE).map((s) => s.light.fg);
    expect(new Set(fgs).size).toBe(fgs.length);
    const ramp = DENSITY_RAMP.map(([, c]) => c);
    for (const s of Object.values(CATEGORY_STYLE)) for (const t of [s.light, s.dark]) expect(ramp).not.toContain(t.fg);
  });

  it("exposes the tones as CSS variables", () => {
    expect(categoryVars("theft")).toEqual({ "--cat-fg": "#1d4ed8", "--cat-bg": "#dbeafe", "--cat-fg-d": "#93c5fd", "--cat-bg-d": "#172554" });
  });

  it("contrast() matches the WCAG reference values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});

describe("density ramp", () => {
  it("is one source for the map paint and the legend", () => {
    expect(densityFill()).toEqual(["interpolate", ["linear"], ["get", "k"], 0, "#fde68a", 0.5, "#f97316", 1, "#b91c1c"]);
    expect(densityGradient()).toBe("linear-gradient(90deg, #fde68a 0%, #f97316 50%, #b91c1c 100%)");
  });
});
