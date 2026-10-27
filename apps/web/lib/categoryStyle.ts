/**
 * Colour and icon per crime category, for badges and chips on the public site (and the console).
 *
 * Hues are kept clear of the map's yellow-to-red density ramp (publicMapTheme.DENSITY_RAMP), so a category
 * colour is never read as "many crimes here". Each entry has a light and a dark pair; the foreground meets
 * WCAG AA (4.5:1) on its own background in both themes (a test checks it).
 *
 * Values are plain hex (Tailwind does not scan lib/); <CategoryBadge> applies them through CSS variables.
 */

export type CategoryIcon =
  | "bag" | "wallet" | "home" | "pulse" | "card" | "shield" | "octagon" | "car" | "dot";

export type CategoryTone = { fg: string; bg: string };
export type CategoryStyle = { icon: CategoryIcon; light: CategoryTone; dark: CategoryTone };

export const CATEGORY_STYLE: Record<string, CategoryStyle> = {
  robbery: { icon: "bag", light: { fg: "#5b21b6", bg: "#ede9fe" }, dark: { fg: "#c4b5fd", bg: "#2e1065" } },
  theft: { icon: "wallet", light: { fg: "#1d4ed8", bg: "#dbeafe" }, dark: { fg: "#93c5fd", bg: "#172554" } },
  house_break: { icon: "home", light: { fg: "#047857", bg: "#d1fae5" }, dark: { fg: "#6ee7b7", bg: "#022c22" } },
  hurt: { icon: "pulse", light: { fg: "#be185d", bg: "#fce7f3" }, dark: { fg: "#f9a8d4", bg: "#500724" } },
  cheating: { icon: "card", light: { fg: "#0e7490", bg: "#cffafe" }, dark: { fg: "#67e8f9", bg: "#083344" } },
  crimes_against_women: { icon: "shield", light: { fg: "#a21caf", bg: "#fae8ff" }, dark: { fg: "#f0abfc", bg: "#4a044e" } },
  homicide: { icon: "octagon", light: { fg: "#334155", bg: "#e2e8f0" }, dark: { fg: "#cbd5e1", bg: "#1e293b" } },
  kidnapping: { icon: "car", light: { fg: "#4338ca", bg: "#e0e7ff" }, dark: { fg: "#a5b4fc", bg: "#1e1b4b" } },
};

export const FALLBACK_STYLE: CategoryStyle = {
  icon: "dot", light: { fg: "#475569", bg: "#f1f5f9" }, dark: { fg: "#cbd5e1", bg: "#1e293b" },
};

/** The style for a category key; unknown or empty keys get the neutral fallback. */
export function categoryStyle(category: string | null | undefined): CategoryStyle {
  return (category && CATEGORY_STYLE[category]) || FALLBACK_STYLE;
}

/** CSS variables for one category, consumed by classes like `bg-[var(--cat-bg)] dark:bg-[var(--cat-bg-d)]`. */
export function categoryVars(category: string | null | undefined): Record<string, string> {
  const s = categoryStyle(category);
  return { "--cat-fg": s.light.fg, "--cat-bg": s.light.bg, "--cat-fg-d": s.dark.fg, "--cat-bg-d": s.dark.bg };
}

/** WCAG relative-luminance contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
