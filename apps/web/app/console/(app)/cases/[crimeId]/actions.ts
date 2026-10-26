"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { moCorrections, type MoField } from "@/lib/cases";
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
