/**
 * Pure helpers for the Pulse Map (spec G3). No deck.gl or DOM imports, so they are unit-tested.
 */

// =====================
// Categories and colours
// =====================

export type CatKey = "homicide" | "robbery" | "burglary" | "vehicle_theft" | "cyber_fraud" | "other";

export const CAT_KEYS: CatKey[] = ["homicide", "robbery", "burglary", "vehicle_theft", "cyber_fraud", "other"];

export const CAT_LABEL: Record<CatKey, string> = {
  homicide: "Homicide", robbery: "Robbery", burglary: "Burglary", vehicle_theft: "Vehicle theft", cyber_fraud: "Cyber / fraud", other: "Other",
};

/** G3 palette: homicide crimson, robbery amber, burglary violet, vehicle theft teal, cyber/fraud blue. */
export const CAT_COLOUR: Record<CatKey, [number, number, number]> = {
  homicide: [220, 20, 60],
  robbery: [255, 176, 32],
  burglary: [150, 100, 255],
  vehicle_theft: [0, 184, 169],
  cyber_fraud: [64, 140, 255],
  other: [160, 170, 180],
};

/** Shape glyph per category for colour-blind users (drawn as text over the dot). */
export const CAT_GLYPH: Record<CatKey, string> = {
  homicide: "✚", robbery: "▲", burglary: "■", vehicle_theft: "◆", cyber_fraud: "●", other: "○",
};

/** Map a free-text category / sub-type to one of the palette keys. */
export function catKey(category: string | null | undefined, subType?: string | null): CatKey {
  const s = `${category ?? ""} ${subType ?? ""}`.toLowerCase();
  if (/homicide|murder|culpable/.test(s)) return "homicide";
  if (/vehicle|motor|bike_theft|auto_theft|car_theft/.test(s)) return "vehicle_theft";
  if (/cyber|fraud|cheat|scam|phish|otp/.test(s)) return "cyber_fraud";
  if (/burglary|house|break|lurking|trespass/.test(s)) return "burglary";
  if (/robbery|snatch|dacoity|extortion|theft/.test(s)) return "robbery";
  return "other";
}

// =====================
// Time
// =====================

export const DAY_MS = 86_400_000;
export const HOUR_MS = 3_600_000;

export type PulseTier = "fast" | "medium" | "static" | "future";

/** G3: pulse period by age at the playhead: < 24 h fast (1.2 s), < 7 days medium, older static. */
export function pulseTier(eventMs: number, playheadMs: number): PulseTier {
  const age = playheadMs - eventMs;
  if (age < 0) return "future";
  if (age < DAY_MS) return "fast";
  if (age < 7 * DAY_MS) return "medium";
  return "static";
}

export const PULSE_PERIOD_MS: Record<"fast" | "medium", number> = { fast: 1200, medium: 2600 };

/** 0..1 pulse phase for an animated ring. */
export function pulsePhase(nowMs: number, tier: "fast" | "medium", seed = 0): number {
  const p = PULSE_PERIOD_MS[tier];
  return (((nowMs + seed * 97) % p) + p) % p / p;
}

/** True when minute-of-day m is inside the clock arc [start, end), which may wrap past midnight. */
export function inClockArc(m: number, start: number, end: number): boolean {
  const s = ((start % 1440) + 1440) % 1440;
  const e = ((end % 1440) + 1440) % 1440;
  if (s === e) return true; // full day
  return s < e ? m >= s && m < e : m >= s || m < e;
}

/** Local day index (days since epoch in the city's timezone) for a UTC instant. */
export function localDay(ms: number, offsetMinutes: number): number {
  return Math.floor((ms + offsetMinutes * 60_000) / DAY_MS);
}

/** Daily histogram between two local day indexes inclusive. */
export function binDaily(times: number[], fromDay: number, toDay: number, offsetMinutes: number): number[] {
  const n = Math.max(0, toDay - fromDay + 1);
  const bins = new Array<number>(n).fill(0);
  for (const t of times) {
    const d = localDay(t, offsetMinutes) - fromDay;
    if (d >= 0 && d < n) bins[d]++;
  }
  return bins;
}

/** Polar histogram for the clock dial: 24 hourly bins of minute-of-day values. */
export function binHours(minutes: number[]): number[] {
  const bins = new Array<number>(24).fill(0);
  for (const m of minutes) if (m >= 0 && m < 1440) bins[Math.floor(m / 60)]++;
  return bins;
}

/** UTC offset in minutes of an IANA timezone at an instant (e.g. Asia/Kolkata → 330). */
export function tzOffsetMinutes(tz: string, at = Date.now()): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).formatToParts(new Date(at));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const local = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
  return Math.round((local - Math.floor(at / 60_000) * 60_000) / 60_000);
}

// =====================
// Geometry
// =====================

export type LonLat = [number, number];

/** Convex hull (Andrew's monotone chain). Returns a closed ring, or [] for fewer than 3 distinct points. */
export function convexHull(points: LonLat[]): LonLat[] {
  const pts = Array.from(new Map(points.map((p) => [`${p[0]},${p[1]}`, p])).values())
    .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return [];
  const cross = (o: LonLat, a: LonLat, b: LonLat) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: LonLat[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: LonLat[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  const hull = lower.slice(0, -1).concat(upper.slice(0, -1));
  return hull.length >= 3 ? [...hull, hull[0]] : [];
}

/** Grow a hull ring away from its centroid so the glow surrounds the member points. */
export function padRing(ring: LonLat[], pad: number): LonLat[] {
  if (ring.length === 0) return ring;
  const body = ring.slice(0, -1);
  const cx = body.reduce((s, p) => s + p[0], 0) / body.length;
  const cy = body.reduce((s, p) => s + p[1], 0) / body.length;
  const out = body.map(([x, y]): LonLat => {
    const dx = x - cx, dy = y - cy;
    const d = Math.hypot(dx, dy) || 1;
    return [x + (dx / d) * pad, y + (dy / d) * pad];
  });
  return [...out, out[0]];
}

/**
 * Sample a gently curved arc from a to b as a path with timestamps 0..1 (for an animated
 * TripsLayer dash that travels from the earlier crime to the later one).
 */
export function arcPath(a: LonLat, b: LonLat, steps = 24, bend = 0.18): { path: LonLat[]; t: number[] } {
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const cx = mx - dy * bend, cy = my + dx * bend; // control point, perpendicular to the chord
  const path: LonLat[] = [];
  const t: number[] = [];
  for (let i = 0; i <= steps; i++) {
    const u = i / steps;
    const x = (1 - u) * (1 - u) * a[0] + 2 * (1 - u) * u * cx + u * u * b[0];
    const y = (1 - u) * (1 - u) * a[1] + 2 * (1 - u) * u * cy + u * u * b[1];
    path.push([x, y]);
    t.push(u);
  }
  return { path, t };
}

/** Haversine distance in km. */
export function km(a: LonLat, b: LonLat): number {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

/**
 * A CCTV camera's view cone as a polygon: apex at the camera, opening `fov` degrees around
 * `heading` (0 = north, clockwise), out to `rangeM` metres.
 */
export function cone(lon: number, lat: number, heading: number, fov: number, rangeM: number, steps = 8): LonLat[] {
  const dLat = rangeM / 111_320;
  const dLon = rangeM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring: LonLat[] = [[lon, lat]];
  for (let i = 0; i <= steps; i++) {
    const ang = ((heading - fov / 2 + (fov * i) / steps) * Math.PI) / 180;
    ring.push([lon + Math.sin(ang) * dLon, lat + Math.cos(ang) * dLat]);
  }
  ring.push([lon, lat]);
  return ring;
}

// =====================
// Columnar crime payload (0004_02 map_crimes)
// =====================

export type MapCrimeCols = {
  id: string[]; lon: number[]; lat: number[]; t: number[]; mod: number[];
  cat: string[]; sub: (string | null)[]; sev: number[]; st: string[]; status: string[];
  linked: boolean[]; series: (string | null)[];
};

export type MapCrime = {
  id: string; pos: LonLat; t: number; mod: number; cat: CatKey; category: string; sub: string | null;
  sev: number; st: string; status: string; linked: boolean; series: string | null;
};

export function decodeCrimes(c: MapCrimeCols | null | undefined): MapCrime[] {
  if (!c || !Array.isArray(c.id)) return [];
  return c.id.map((id, i) => ({
    id, pos: [c.lon[i], c.lat[i]], t: c.t[i], mod: c.mod[i], cat: catKey(c.cat[i], c.sub[i]), category: c.cat[i],
    sub: c.sub[i], sev: c.sev[i], st: c.st[i], status: c.status[i], linked: !!c.linked[i], series: c.series[i] ?? null,
  }));
}

/** Month windows [from, to) covering a range, newest first, so recent data paints first. */
export function monthWindows(fromMs: number, toMs: number): [number, number][] {
  const out: [number, number][] = [];
  const d = new Date(fromMs);
  let cur = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  while (cur <= toMs) {
    const n = new Date(cur);
    const next = Date.UTC(n.getUTCFullYear(), n.getUTCMonth() + 1, 1);
    out.push([cur, next]);
    cur = next;
  }
  return out.reverse();
}

// =====================
// Filters
// =====================

export type CrimeFilter = {
  cats: Set<CatKey>;
  from: number; to: number;           // time window (ms)
  clock: [number, number] | null;     // minute-of-day arc, null = all day
  linkedOnly: boolean;
  seriesOnly: boolean;
  stations: Set<string>;              // empty = all (a zone filter arrives here as its stations)
  statuses: Set<string>;              // empty = all
  ids?: Set<string> | null;           // weapon / vehicle / MO matches (facetIds); null or absent = all
};

export function passes(c: MapCrime, f: CrimeFilter): boolean {
  if (!f.cats.has(c.cat)) return false;
  if (c.t < f.from || c.t > f.to) return false;
  if (f.clock && !inClockArc(c.mod, f.clock[0], f.clock[1])) return false;
  if (f.linkedOnly && !c.linked) return false;
  if (f.seriesOnly && !c.series) return false;
  if (f.stations.size && !f.stations.has(c.st)) return false;
  if (f.statuses.size && !f.statuses.has(c.status)) return false;
  if (f.ids && !f.ids.has(c.id)) return false;
  return true;
}

/** "19:00" from minutes. */
export function hhmm(m: number): string {
  const x = ((Math.round(m) % 1440) + 1440) % 1440;
  return `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
}

// =====================
// ISO weeks (layers bucketed by week: 112 calls, tips)
// =====================

/** ISO-8601 week label ("2026-W43") of an instant in the city's timezone. */
export function isoWeek(ms: number, offsetMinutes: number): string {
  const local = new Date(ms + offsetMinutes * 60_000);
  const d = new Date(Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate()));
  const day = d.getUTCDay() || 7; // Mon=1..Sun=7
  d.setUTCDate(d.getUTCDate() + 4 - day); // Thursday of this week decides the year
  const year = d.getUTCFullYear();
  const week = Math.ceil(((d.getTime() - Date.UTC(year, 0, 1)) / DAY_MS + 1) / 7);
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** True when an ISO week label falls inside [from, to] (labels compare as strings). */
export function weekInRange(week: string, from: string, to: string): boolean {
  return week >= from && week <= to;
}

/**
 * [west, south, east, north] around the points, padded by `pad` degrees (a single point still gets an area);
 * null when there are no points.
 */
export function boundsOf(points: LonLat[], pad = 0.01): [number, number, number, number] | null {
  if (points.length === 0) return null;
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const [lon, lat] of points) {
    if (lon < w) w = lon; if (lon > e) e = lon; if (lat < s) s = lat; if (lat > n) n = lat;
  }
  return [w - pad, s - pad, e + pad, n + pad];
}

/**
 * The opening camera frame: the crimes the role can see in the window (outliers trimmed to the
 * 2nd-98th percentile once there are enough to trim), plus every arc end and series member so the
 * links on screen are never cut off. null when there is nothing to frame (keep the city view).
 */
export function initialFrame(points: LonLat[], linked: LonLat[], pad = 0.008): [number, number, number, number] | null {
  let core = points;
  if (points.length > 40) {
    const q = (xs: number[], f: number) => xs[Math.min(xs.length - 1, Math.max(0, Math.floor(f * (xs.length - 1))))];
    const lons = points.map((p) => p[0]).sort((a, b) => a - b), lats = points.map((p) => p[1]).sort((a, b) => a - b);
    const w = q(lons, 0.02), e = q(lons, 0.98), s = q(lats, 0.02), n = q(lats, 0.98);
    core = points.filter(([lon, lat]) => lon >= w && lon <= e && lat >= s && lat <= n);
  }
  return boundsOf(core.concat(linked), pad);
}

export type Box = { left: number; top: number; right: number; bottom: number };
export type Padding = { top: number; bottom: number; left: number; right: number };

/**
 * Camera padding that keeps a fitted frame clear of the map's floating panels. Each panel pads the
 * side it hugs (the cheapest of its four), plus a margin; if the panels would leave less than a
 * share of the map, that axis is scaled down so the frame never collapses (phones).
 */
export function overlayPadding(box: Box, panels: Box[], margin = 16, minShare = 0.4): Padding {
  const W = box.right - box.left, H = box.bottom - box.top;
  const p: Padding = { top: margin, bottom: margin, left: margin, right: margin };
  for (const r of panels) {
    if (r.right <= box.left || r.left >= box.right || r.bottom <= box.top || r.top >= box.bottom) continue;
    const c: [keyof Padding, number, number][] = [
      ["top", r.bottom - box.top, W], ["bottom", box.bottom - r.top, W],
      ["left", r.right - box.left, H], ["right", box.right - r.left, H],
    ];
    // cost = map area given up by padding that side
    const [side, d] = c.reduce((best, x) => (x[1] * x[2] < best[1] * best[2] ? x : best));
    p[side] = Math.max(p[side], d + margin);
  }
  const fit = (a: keyof Padding, b: keyof Padding, total: number) => {
    const room = total * (1 - minShare);
    if (p[a] + p[b] > room) { const k = room / (p[a] + p[b]); p[a] = Math.round(p[a] * k); p[b] = Math.round(p[b] * k); }
  };
  fit("left", "right", W);
  fit("top", "bottom", H);
  return p;
}

// =====================
// DASH-04: station / zone / status / weapon / vehicle / MO filters
// =====================

/** Bucket for stations with no zone in the registry, so they can still be chosen. */
export const UNKNOWN_ZONE = "Unknown";

export type FacetStation = { id: string; name: string; zone: string | null };
export type Facets = {
  stations: FacetStation[];
  weapon: Map<string, Set<string>>;
  vehicle: Map<string, Set<string>>;
  mo: Map<string, Set<string>>;
};
export type FacetSelection = { weapon: Set<string>; vehicle: Set<string>; mo: Set<string> };

/** The stations of the chosen zones; an empty set when no zone is chosen (no restriction). */
export function zoneStations(stations: { id: string; zone: string | null }[], zones: Set<string>): Set<string> {
  const out = new Set<string>();
  if (zones.size === 0) return out;
  for (const st of stations) if (zones.has(st.zone ?? UNKNOWN_ZONE)) out.add(st.id);
  return out;
}

function idMap(v: unknown): Map<string, Set<string>> {
  const m = new Map<string, Set<string>>();
  if (!v || typeof v !== "object" || Array.isArray(v)) return m;
  for (const [k, ids] of Object.entries(v as Record<string, unknown>)) {
    if (Array.isArray(ids)) m.set(k, new Set(ids.filter((x): x is string => typeof x === "string")));
  }
  return m;
}

/** map_facets() payload (0004_12) to typed sets; anything malformed becomes empty, never an exception. */
export function decodeFacets(raw: unknown): Facets {
  const o = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const stations = Array.isArray(o.stations)
    ? o.stations.flatMap((r) => (Array.isArray(r) && typeof r[0] === "string"
      ? [{ id: r[0], name: typeof r[1] === "string" ? r[1] : r[0], zone: typeof r[2] === "string" && r[2] ? r[2] : null }]
      : []))
    : [];
  return { stations, weapon: idMap(o.weapon), vehicle: idMap(o.vehicle), mo: idMap(o.mo) };
}

/** Facet values, most crimes first (ties alphabetical), so common tags lead and one-offs sink. */
export function byCount(m: Map<string, Set<string>>): string[] {
  return Array.from(m.entries()).sort((a, b) => b[1].size - a[1].size || a[0].localeCompare(b[0])).map(([k]) => k);
}

/**
 * Crime ids matching the weapon / vehicle / MO choices: any chosen value within a kind (OR), every kind
 * that has a choice (AND). null when nothing is chosen, so the filter does not restrict at all.
 */
export function facetIds(f: Facets, sel: FacetSelection): Set<string> | null {
  const kinds: [keyof FacetSelection, Set<string>][] = [["weapon", sel.weapon], ["vehicle", sel.vehicle], ["mo", sel.mo]];
  const perKind: Set<string>[] = [];
  for (const [kind, chosen] of kinds) {
    if (chosen.size === 0) continue;
    const any = new Set<string>();
    for (const v of Array.from(chosen)) for (const id of Array.from(f[kind].get(v) ?? [])) any.add(id);
    perKind.push(any);
  }
  if (perKind.length === 0) return null;
  return perKind.reduce((acc, ids) => new Set(Array.from(acc).filter((id) => ids.has(id))));
}

/** Map label for a series hull: "<name> · N cases · M stations", without repeating a station count the name already carries. */
export function seriesLabel(name: string, cases: number, stations: number): string {
  const st = /\bstations?\b/i.test(name) ? "" : ` · ${stations} station${stations === 1 ? "" : "s"}`;
  return `${name} · ${cases} case${cases === 1 ? "" : "s"}${st}`;
}
