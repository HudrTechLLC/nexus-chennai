/**
 * Light / dark basemap for the public maps (crime map, appeal area map, tip area picker). The style and the
 * outline colours follow the visitor's prefers-color-scheme, matching the page tokens in globals.css.
 */
export type MapTheme = "light" | "dark";

type MatchMedia = (query: string) => { matches: boolean };

/** The visitor's preference; "light" when there is no browser (server render, tests). */
export function currentMapTheme(matchMedia?: MatchMedia): MapTheme {
  const mm = matchMedia ?? (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia.bind(window) : null);
  return mm && mm("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export const mapStyleUrl = (t: MapTheme) => `/map/${t}.json`;

/** Outline colours: `signal` = --signal, `selected` = --ink, per theme (globals.css). */
export const MAP_INK: Record<MapTheme, { signal: string; selected: string }> = {
  light: { signal: "#0e7c86", selected: "#111827" },
  dark: { signal: "#45c2cc", selected: "#e4eaf1" },
};

/**
 * Hexagon fill on the public crime map: count relative to the busiest visible hexagon (k = n / max), from pale
 * yellow to deep red. The map paint and the legend both read this, so they cannot drift apart.
 */
export const DENSITY_RAMP: ReadonlyArray<readonly [number, string]> = [[0, "#fde68a"], [0.5, "#f97316"], [1, "#b91c1c"]];
export const HEX_FILL_OPACITY = 0.55;

/** The ramp as a MapLibre `interpolate` expression over the feature's `k`. */
export const densityFill = () => ["interpolate", ["linear"], ["get", "k"], ...DENSITY_RAMP.flat()];

/** The ramp as a CSS gradient, for the legend. */
export const densityGradient = () => `linear-gradient(90deg, ${DENSITY_RAMP.map(([at, c]) => `${c} ${at * 100}%`).join(", ")})`;
