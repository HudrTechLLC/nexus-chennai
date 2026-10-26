/**
 * Vehicles register (CAP-06, /console/vehicles): pure filter parsing and grouping.
 * Data access is in the page; rows come from crime_vehicles under RLS (can_read_crime).
 */
import { normalisePlate } from "@/lib/cases";

export const VEHICLE_TYPES = ["motorcycle", "car", "scooter", "auto_rickshaw", "van", "truck"] as const;

export type VehicleFilters = {
  plate: string | null; // normalised fragment, "?" = unknown character
  type: string | null;
  make: string | null;
  colour: string | null;
};

export type VehicleRow = {
  crime_id: string;
  plate_pattern: string | null;
  vehicle_type: string;
  make_model: string | null;
  colour: string | null;
  role: string;
};

export type VehicleGroup = {
  /** The plate as recorded, or null for rows whose plate was not read (each stays its own entry). */
  plate: string | null;
  vehicle_type: string;
  make_model: string | null;
  colour: string | null;
  roles: string[];
  crimes: string[];
};

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)?.trim() ?? "";
const word = (v: string) => (/^[a-z0-9 -]{2,30}$/i.test(v) ? v.toLowerCase() : null);

export function parseVehicleFilters(sp: Record<string, string | string[] | undefined>): VehicleFilters {
  const type = one(sp.type).toLowerCase();
  return {
    plate: one(sp.plate) ? normalisePlate(one(sp.plate)) : null,
    type: (VEHICLE_TYPES as readonly string[]).includes(type) ? type : null,
    make: word(one(sp.make)),
    colour: word(one(sp.colour)),
  };
}

export function hasVehicleFilter(f: VehicleFilters): boolean {
  return !!(f.plate || f.type || f.make || f.colour);
}

/** The most common non-empty value, ties broken alphabetically. */
function mode(values: (string | null)[]): string | null {
  const n = new Map<string, number>();
  for (const v of values) if (v) n.set(v, (n.get(v) ?? 0) + 1);
  return Array.from(n).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
}

/**
 * One entry per recorded plate (the same plate on several cases is one vehicle with several cases),
 * most cases first. Rows without a plate are kept as separate entries: nothing says they are the same vehicle.
 */
export function groupVehicles(rows: VehicleRow[]): VehicleGroup[] {
  const byPlate = new Map<string, VehicleRow[]>();
  const unread: VehicleGroup[] = [];
  for (const r of rows) {
    const plate = r.plate_pattern?.trim().toUpperCase() || null;
    if (!plate) {
      unread.push({ plate: null, vehicle_type: r.vehicle_type, make_model: r.make_model, colour: r.colour, roles: [r.role], crimes: [r.crime_id] });
      continue;
    }
    byPlate.set(plate, [...(byPlate.get(plate) ?? []), r]);
  }
  const grouped = Array.from(byPlate, ([plate, rs]) => ({
    plate,
    vehicle_type: mode(rs.map((r) => r.vehicle_type)) ?? rs[0].vehicle_type,
    make_model: mode(rs.map((r) => r.make_model)),
    colour: mode(rs.map((r) => r.colour)),
    roles: Array.from(new Set(rs.map((r) => r.role))).sort(),
    crimes: Array.from(new Set(rs.map((r) => r.crime_id))).sort(),
  })).sort((a, b) => b.crimes.length - a.crimes.length || a.plate.localeCompare(b.plate));
  return [...grouped, ...unread];
}

/** ANPR reads per exact plate (reads store full plates; partial "?" plates never match exactly). */
export function readsPerPlate(reads: { plate_text: string }[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const r of reads) {
    const k = r.plate_text.replace(/\s+/g, "").toUpperCase();
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return m;
}
