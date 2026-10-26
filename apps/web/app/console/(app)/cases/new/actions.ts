"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { allows } from "@/lib/roles";
import { CITY } from "@/lib/city";
import { toPayload, validateFir, type FirForm } from "@/lib/fir";
import { consoleServerClient } from "@/lib/supabase/server";

export type FileResult = { ok: true; crimeId: string } | { ok: false; error: string; fields?: Record<string, string> };
export type PlaceResult = { wardNo: number | null; wardName: string | null; stationId: string | null; stationName: string | null };

const FILERS = ["station_officer", "admin"] as const;

/**
 * Files a FIR through public.file_fir (0007_01) as the signed-in officer: crime, vehicles and typed
 * statements land in one transaction, then the local worker picks the case up for extraction and
 * linking (process_new_cases). Nothing here calls a model; MO extraction happens after save (R3).
 */
export async function fileFir(form: FirForm): Promise<FileResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  if (!allows(officer.role, [...FILERS])) return { ok: false, error: "Only station officers file FIRs." };
  if (officer.role !== "admin") delete form.station_id;
  else if (!form.station_id) return { ok: false, error: "Choose the station.", fields: { station_id: "Choose the station." } };

  const fields = validateFir(form, { tz: CITY.timezone, bounds: CITY.map.bounds });
  if (Object.keys(fields).length) return { ok: false, error: "Check the highlighted fields.", fields };

  const sb = consoleServerClient();
  const { data, error } = await sb.rpc("file_fir", { p: toPayload(form, CITY.timezone, { r8: 8, r9: 9 }) });
  if (error) {
    const msg = error.code === "42501" ? `Not allowed: ${error.message}` : error.code === "22023" ? error.message : `Could not file the FIR: ${error.message}`;
    return { ok: false, error: msg };
  }
  revalidatePath("/console/cases");
  return { ok: true, crimeId: data as string };
}

/** Ward and police station whose boundaries contain the picked point (for the jurisdiction warning). */
export async function placeCheck(lat: number, lon: number): Promise<PlaceResult> {
  const empty = { wardNo: null, wardName: null, stationId: null, stationName: null };
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return empty;
  const officer = await getOfficer();
  if (!officer) return empty;
  const { data } = await consoleServerClient().rpc("fir_place_check", { p_lat: lat, p_lon: lon }).maybeSingle();
  const r = data as { ward_no: number | null; ward_name: string | null; station_id: string | null; station_name: string | null } | null;
  return r ? { wardNo: r.ward_no, wardName: r.ward_name, stationId: r.station_id, stationName: r.station_name } : empty;
}
