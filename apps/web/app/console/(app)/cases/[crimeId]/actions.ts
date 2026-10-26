"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { canSetStatus, canWriteCase, moCorrections, validateDiary, type MoField } from "@/lib/cases";
import { audit } from "@/lib/alertsData";
import { CITY } from "@/lib/city";
import { cityLocalToIso } from "@/lib/fir";
import { consoleServerClient } from "@/lib/supabase/server";

export type ReviewResult = { ok: true; changed: number } | { ok: false; error: string };

/**
 * Officer review of the Extractor's MO (spec G2 "MO features (editable)", chief's decision): the
 * corrections go to crime_feature_reviews via review_features (0007_01), never into crime_features,
 * so the model output keeps its provenance (R3). An empty correction still records "reviewed".
 */
export async function reviewMo(crimeId: string, edited: Partial<Record<MoField, string>>, note: string): Promise<ReviewResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const sb = consoleServerClient();
  const { data: f } = await sb.from("crime_features").select("mo").eq("crime_id", crimeId).maybeSingle();
  if (!f) return { ok: false, error: "The Extractor has not run on this case yet." };
  const diff = moCorrections((f.mo ?? {}) as Record<string, unknown>, edited);
  if ("error" in diff) return { ok: false, error: diff.error };
  const { error } = await sb.rpc("review_features", { p_crime_id: crimeId, p_corrections: diff.corrections, p_note: note.slice(0, 1000) || null });
  if (error) return { ok: false, error: error.code === "42501" ? "Only the case's station (or a supervisor) can review its MO." : error.message };
  revalidatePath(`/console/cases/${encodeURIComponent(crimeId)}`);
  return { ok: true, changed: Object.keys(diff.corrections).length };
}

export type WriteResult = { ok: true } | { ok: false; error: string };

/** Case diary entry (CAP-04) as the officer; RLS "add case_diary" checks can_write_crime. */
export async function addDiaryEntry(crimeId: string, entry: { kind: string; text: string; at: string }): Promise<WriteResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const problem = validateDiary(entry, new Date(), (l) => cityLocalToIso(l, CITY.timezone));
  if (problem) return { ok: false, error: problem };
  const sb = consoleServerClient();
  const at = entry.at ? (cityLocalToIso(entry.at, CITY.timezone) as string) : new Date().toISOString();
  const { error } = await sb.from("case_diary").insert({
    entry_id: `CD-${crypto.randomUUID()}`, crime_id: crimeId, at, kind: entry.kind, text: entry.text.trim(),
    author: officer.name, synthetic: CITY.synthetic,
  });
  if (error) return { ok: false, error: error.code === "42501" ? "Only the case's station (or a supervisor) can add diary entries." : error.message };
  await audit(sb, "add_diary_entry", "crime", crimeId, { kind: entry.kind });
  revalidatePath(`/console/cases/${encodeURIComponent(crimeId)}`);
  return { ok: true };
}

/** Moves a case to a new status (CAP-01) as the officer; RLS "officers update own station crimes". */
export async function setCaseStatus(crimeId: string, to: string): Promise<WriteResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const sb = consoleServerClient();
  const { data: c } = await sb.from("crimes").select("station_id, status").eq("crime_id", crimeId).maybeSingle();
  if (!c) return { ok: false, error: "Case not found." };
  if (!canWriteCase(officer.role, officer.stationId, c.station_id)) return { ok: false, error: "Only the case's station (or a supervisor) can change its status." };
  if (!canSetStatus(c.status, to)) return { ok: false, error: "Choose a different status." };
  const { data, error } = await sb.from("crimes").update({ status: to }).eq("crime_id", crimeId).select("status");
  if (error) return { ok: false, error: error.message };
  if (!data?.length) return { ok: false, error: "The status was not changed (not allowed for your role)." };
  await audit(sb, "set_case_status", "crime", crimeId, { from: c.status, to });
  revalidatePath(`/console/cases/${encodeURIComponent(crimeId)}`);
  revalidatePath("/console/cases");
  return { ok: true };
}
