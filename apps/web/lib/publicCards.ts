/**
 * Public crime cards on /map (WS4-11; 0007_11 public_hex_crimes / public_crime).
 * Pure helpers: the map state kept in the URL (so "Back to map" restores hex, window, type and position),
 * plain-English labels and links. Cards carry only public fields; there is no crime id here.
 */

/** One public card, exactly as public_hex_crimes / public_crime return it. */
export type CrimeCard = {
  public_id: string;
  category: string;
  sub_type: string | null;
  week: string;
  time_window: "morning" | "afternoon" | "evening" | "night";
  cell: string;
  area: string | null;
  status: "open" | "charge-sheeted" | "closed";
  in_pattern: boolean;
  mo_summary: string | null;
  appeals: { id: string; title: string }[];
};

export type HexCrimes = { cell: string; days: number; area: string | null; cards: CrimeCard[] };

export const MAP_DAYS = [7, 30, 90] as const;
export type MapDays = (typeof MAP_DAYS)[number];

/** Map view in the URL: [lng, lat, zoom], rounded. */
export type MapAt = [number, number, number];
export type MapState = { days: MapDays; type: string | null; hex: string | null; at: MapAt | null };

const HEX_RE = /^88[0-9a-f]{13}$/;
const TYPE_RE = /^[a-z_]{1,40}$/;
const PUBLIC_ID_RE = /^PC-[0-9A-F]{12}$/;

type Params = URLSearchParams | Record<string, string | string[] | undefined>;

function param(p: Params, key: string): string | null {
  if (p instanceof URLSearchParams) return p.get(key);
  const v = p[key];
  return Array.isArray(v) ? v[0] ?? null : v ?? null;
}

const round = (n: number, d: number) => Math.round(n * 10 ** d) / 10 ** d;

function parseAt(s: string | null): MapAt | null {
  if (!s) return null;
  const parts = s.split(",");
  if (parts.length !== 3) return null;
  const [lng, lat, zoom] = parts.map(Number);
  // Chennai and surroundings only; anything else is ignored rather than trusted.
  if (![lng, lat, zoom].every(Number.isFinite) || lng < 79 || lng > 81.5 || lat < 12 || lat > 14 || zoom < 8 || zoom > 18) return null;
  return [round(lng, 4), round(lat, 4), round(zoom, 2)];
}

/** Read the map state from the URL; anything malformed falls back to the default. */
export function parseMapState(p: Params): MapState {
  const d = Number(param(p, "days"));
  const type = param(p, "type");
  const hex = param(p, "hex") ?? param(p, "cell")?.toLowerCase() ?? null; // ?cell= from appeal pages (#282)
  return {
    days: (MAP_DAYS as readonly number[]).includes(d) ? (d as MapDays) : 30,
    type: type && TYPE_RE.test(type) ? type : null,
    hex: hex && HEX_RE.test(hex) ? hex : null,
    at: parseAt(param(p, "at")),
  };
}

/** The URL query for a map state (no leading "?"); defaults and empty values are left out. */
export function mapStateQuery(s: MapState): string {
  const q = new URLSearchParams();
  if (s.days !== 30) q.set("days", String(s.days));
  if (s.type) q.set("type", s.type);
  if (s.hex) q.set("hex", s.hex);
  if (s.at) q.set("at", s.at.map((n, i) => String(i < 2 ? round(n, 4) : round(n, 2))).join(","));
  return q.toString().replaceAll("%2C", ",");
}

const withQuery = (path: string, q: string) => (q ? `${path}?${q}` : path);

export const mapHref = (s: MapState) => withQuery("/map", mapStateQuery(s));
export const crimeHref = (publicId: string, s: MapState) => withQuery(`/map/crime/${publicId}`, mapStateQuery(s));
export const tipHref = (publicId: string) => `/tip/new?about=${encodeURIComponent(publicId)}`;

export const isPublicId = (s: string) => PUBLIC_ID_RE.test(s);

/** "chain_snatching" -> "Chain snatching". */
export const labelOf = (slug: string) => slug.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());

/** "Robbery · Chain snatching"; the sub-type is left out when it only repeats the category. */
export function cardTitle(c: Pick<CrimeCard, "category" | "sub_type">): string {
  return c.sub_type && c.sub_type !== c.category ? `${labelOf(c.category)} · ${labelOf(c.sub_type)}` : labelOf(c.category);
}

/** Case status in plain words: no names or dates (chief: "Charge sheet filed"). */
export const STATUS_LABEL: Record<CrimeCard["status"], string> = {
  open: "Open",
  "charge-sheeted": "Charge sheet filed",
  closed: "Closed",
};

/** "2026-W42" -> "Week 42, 2026". */
export function weekLabel(week: string): string {
  const m = /^(\d{4})-W(\d{2})$/.exec(week);
  return m ? `Week ${Number(m[2])}, ${m[1]}` : week;
}

/** Panel width on md+ screens (HexPanel: md:w-96 = 24rem) plus its offset. */
const PANEL_PX = 384 + 24;

/**
 * Padding for framing a selected hexagon so the HexPanel never covers it: room for the panel on the left on
 * desktop (md+), and above the bottom sheet on mobile. Capped so a small map can still show the hexagon.
 */
export function framePadding(width: number, height: number): { top: number; bottom: number; left: number; right: number } {
  if (width >= 768) {
    const left = Math.min(PANEL_PX + 12, Math.max(0, width - 260));
    return { top: 40, bottom: 40, left, right: 40 };
  }
  return { top: 30, bottom: Math.min(Math.round(height * 0.5), Math.max(0, height - 150)), left: 30, right: 30 };
}
