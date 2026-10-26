/**
 * FIR capture (spec G4): form shape, validation and the payload for public.file_fir (0007_01).
 * Pure, so the server action, the form and the tests share one copy.
 */
import { latLngToCell } from "h3-js";
import { CRIME_TYPES } from "@/lib/cases";

// =====================
// Types
// =====================

export type FirVehicle = { role: string; vehicle_type: string; plate_pattern: string; make_model: string; colour: string };
export type FirOffender = { count: string; build: string; age_band: string; helmet: string; clothing: string; marks: string };
export type FirVictim = { gender: string; age_band: string };
export type FirProperty = { item: string; value_inr: string };

/** What the form submits. Times are city wall-clock "YYYY-MM-DDTHH:mm" from datetime-local inputs. */
export type FirForm = {
  station_id?: string; // admin only
  category: string;
  sub_type: string;
  sections: string[];
  occurred_from: string;
  occurred_to: string;
  lat: number | null;
  lon: number | null;
  address: string;
  severity: number;
  weapon: string;
  property: FirProperty[];
  offenders: FirOffender[];
  victims: FirVictim[];
  vehicles: FirVehicle[];
  narrative: string;
  statements: string[];
};

export const VEHICLE_ROLES = ["used_by_offender", "stolen", "victim_vehicle"] as const;
export const VEHICLE_TYPES = ["motorcycle", "scooter", "car", "auto", "van", "truck", "bicycle", "unknown"] as const;
export const AGE_BANDS = ["under_18", "18-20", "20-30", "30-40", "40-50", "50-60", "60+"] as const;
export const BUILDS = ["thin", "medium", "heavy"] as const;
export const GENDERS = ["F", "M", "X"] as const;

export const LIMITS = { narrative: 4000, statement: 4000, address: 200, statements: 10, vehicles: 6, people: 8 } as const;

// =====================
// Time
// =====================

/** Offset in minutes of a time zone at an instant (e.g. +330 for Asia/Kolkata). */
export function tzOffsetMinutes(tz: string, at: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(at);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  return Math.round((asUtc - at.getTime()) / 60000);
}

/** "2026-10-26T18:20" read as wall-clock time in `tz` → ISO instant; null when malformed. */
export function cityLocalToIso(local: string, tz: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null;
  const naive = new Date(`${local}:00Z`);
  if (Number.isNaN(naive.getTime())) return null;
  const offset = tzOffsetMinutes(tz, new Date(naive.getTime() - tzOffsetMinutes(tz, naive) * 60000));
  return new Date(naive.getTime() - offset * 60000).toISOString();
}

// =====================
// Geo
// =====================

const B32 = "0123456789bcdefghjkmnpqrstuvwxyz";

/** Standard geohash (precision 7 ≈ 150 m), the same encoding the seed uses for crimes.geohash7. */
export function geohash(lat: number, lon: number, precision = 7): string {
  let latR: [number, number] = [-90, 90];
  let lonR: [number, number] = [-180, 180];
  let out = "";
  let bit = 0;
  let ch = 0;
  let even = true;
  while (out.length < precision) {
    const r = even ? lonR : latR;
    const v = even ? lon : lat;
    const mid = (r[0] + r[1]) / 2;
    ch <<= 1;
    if (v >= mid) {
      ch |= 1;
      r[0] = mid;
    } else {
      r[1] = mid;
    }
    if (even) lonR = r; else latR = r;
    even = !even;
    if (++bit === 5) {
      out += B32[ch];
      bit = 0;
      ch = 0;
    }
  }
  return out;
}

/** True when a point is inside the city's map bounds [west, south, east, north]. */
export function inBounds(lat: number, lon: number, b: [number, number, number, number]): boolean {
  return lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3];
}

// =====================
// Validation
// =====================

/** Field → message. Empty object means the form can be filed. */
export function validateFir(f: FirForm, opts: { tz: string; bounds: [number, number, number, number]; now?: Date }): Record<string, string> {
  const e: Record<string, string> = {};
  const now = opts.now ?? new Date();
  if (!CRIME_TYPES[f.category]) e.category = "Choose a category.";
  else if (f.sub_type && !CRIME_TYPES[f.category].includes(f.sub_type)) e.sub_type = "Choose a sub-type of this category.";
  if (f.sections.length === 0) e.sections = "Add at least one section.";
  const from = cityLocalToIso(f.occurred_from, opts.tz);
  const to = f.occurred_to ? cityLocalToIso(f.occurred_to, opts.tz) : null;
  if (!from) e.occurred_from = "Enter when it happened.";
  else if (Date.parse(from) > now.getTime()) e.occurred_from = "This is in the future.";
  if (f.occurred_to && !to) e.occurred_to = "Enter a valid time.";
  else if (from && to && Date.parse(to) < Date.parse(from)) e.occurred_to = "Ends before it starts.";
  else if (to && Date.parse(to) > now.getTime()) e.occurred_to = "This is in the future.";
  if (f.lat === null || f.lon === null || !Number.isFinite(f.lat) || !Number.isFinite(f.lon)) e.place = "Pick the place on the map.";
  else if (!inBounds(f.lat, f.lon, opts.bounds)) e.place = "The place is outside the city.";
  if (f.address.length > LIMITS.address) e.address = "Address is too long.";
  if (!(f.severity >= 1 && f.severity <= 5)) e.severity = "Severity must be 1–5.";
  if (!f.narrative.trim()) e.narrative = "Write what happened.";
  else if (f.narrative.length > LIMITS.narrative) e.narrative = `Keep it under ${LIMITS.narrative} characters.`;
  if (f.statements.length > LIMITS.statements || f.statements.some((s) => s.length > LIMITS.statement)) e.statements = "Too many or too long statements.";
  if (f.vehicles.length > LIMITS.vehicles) e.vehicles = "Too many vehicles.";
  f.vehicles.forEach((v, i) => {
    if (v.plate_pattern && !/^[A-Za-z0-9?\s-]{2,14}$/.test(v.plate_pattern)) e[`vehicles.${i}`] = "Plate: letters, digits and ? for unread characters.";
  });
  if (f.offenders.length > LIMITS.people || f.victims.length > LIMITS.people || f.property.length > LIMITS.people) e.people = "Too many entries.";
  f.property.forEach((p, i) => {
    if (p.value_inr && !/^\d{1,9}$/.test(p.value_inr)) e[`property.${i}`] = "Value in whole rupees.";
  });
  return e;
}

// =====================
// Payload for file_fir
// =====================

const compact = <T extends Record<string, unknown>>(o: T) =>
  Object.fromEntries(Object.keys(o).filter((k) => o[k] !== "" && o[k] !== null && o[k] !== undefined).map((k) => [k, o[k]]));

/** Turns a valid form into the jsonb the RPC takes. Location cells are computed here (nexus-1 contract). */
export function toPayload(f: FirForm, tz: string, h3Res: { r8: number; r9: number } = { r8: 8, r9: 9 }) {
  const lat = f.lat as number;
  const lon = f.lon as number;
  return {
    ...(f.station_id ? { station_id: f.station_id } : {}),
    category: f.category,
    sub_type: f.sub_type || null,
    sections: Array.from(new Set(f.sections)),
    occurred_from: cityLocalToIso(f.occurred_from, tz),
    occurred_to: f.occurred_to ? cityLocalToIso(f.occurred_to, tz) : null,
    lat, lon,
    address: f.address.trim() || null,
    h3_r8: latLngToCell(lat, lon, h3Res.r8),
    h3_r9: latLngToCell(lat, lon, h3Res.r9),
    geohash7: geohash(lat, lon, 7),
    severity: f.severity,
    weapon: f.weapon.trim() || null,
    property: f.property.filter((p) => p.item.trim()).map((p) => compact({ item: p.item.trim(), value_inr: p.value_inr ? Number(p.value_inr) : null })),
    offenders_described: f.offenders.map((o) => compact({
      count: o.count ? Number(o.count) : null, build: o.build, age_band: o.age_band, helmet: o.helmet.trim(), clothing: o.clothing.trim(), marks: o.marks.trim(),
    })).filter((o) => Object.keys(o).length > 0),
    victims: f.victims.map((v) => compact({ gender: v.gender, age_band: v.age_band })).filter((v) => Object.keys(v).length > 0),
    vehicles: f.vehicles
      .filter((v) => v.plate_pattern.trim() || v.make_model.trim() || v.colour.trim() || v.vehicle_type)
      .map((v) => ({ role: v.role, vehicle_type: v.vehicle_type || "unknown", plate_pattern: v.plate_pattern.trim(), make_model: v.make_model.trim(), colour: v.colour.trim() })),
    narrative: f.narrative.trim(),
    statements: f.statements.map((s) => s.trim()).filter(Boolean).map((text) => ({ text })),
    tz,
  };
}

export function emptyFir(): FirForm {
  return {
    category: "", sub_type: "", sections: [], occurred_from: "", occurred_to: "", lat: null, lon: null, address: "",
    severity: 3, weapon: "", property: [], offenders: [], victims: [], vehicles: [], narrative: "", statements: [],
  };
}
