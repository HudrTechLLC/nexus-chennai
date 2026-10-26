import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { rankSimilar, type SimilarHit, type SimilarInput } from "@/lib/similar";

const COLS = "crime_id, station_id, category, sub_type, cell, week, mo_tags, visual_tags";

/**
 * Look-alike cases for one crime, from crimes_citywide (summary columns every police role may
 * read, so other stations' cases appear too, without narrative or address). Returns null when the
 * case has no extracted features yet, because there is nothing to compare.
 */
export async function fetchSimilar(sb: SupabaseClient, crimeId: string, limit = 8): Promise<{ self: SimilarInput; hits: SimilarHit[] } | null> {
  const { data: self } = await sb.from("crimes_citywide").select(COLS).eq("crime_id", crimeId).maybeSingle();
  const me = self as SimilarInput | null;
  if (!me || ((me.mo_tags ?? []).length === 0 && (me.visual_tags ?? []).length === 0)) return null;
  const [byMo, byVisual] = await Promise.all([
    (me.mo_tags ?? []).length
      ? sb.from("crimes_citywide").select(COLS).eq("category", me.category).overlaps("mo_tags", me.mo_tags ?? []).limit(300)
      : Promise.resolve({ data: [] }),
    (me.visual_tags ?? []).length
      ? sb.from("crimes_citywide").select(COLS).overlaps("visual_tags", me.visual_tags ?? []).limit(150)
      : Promise.resolve({ data: [] }),
  ]);
  const seen = new Map<string, SimilarInput>();
  for (const c of [...((byMo.data ?? []) as SimilarInput[]), ...((byVisual.data ?? []) as SimilarInput[])]) seen.set(c.crime_id, c);
  return { self: me, hits: rankSimilar(me, Array.from(seen.values()), limit) };
}

/** Cases whose visual or MO tags match a typed phrase (SRCH-06), exact tag match on the variants. */
export async function fetchByTags(sb: SupabaseClient, variants: string[], limit = 50): Promise<{ rows: SimilarInput[]; error: string | null }> {
  if (variants.length === 0) return { rows: [], error: null };
  const { data, error } = await sb.from("crimes_citywide").select(COLS)
    .or(`visual_tags.ov.{${variants.map((v) => `"${v}"`).join(",")}},mo_tags.ov.{${variants.map((v) => `"${v}"`).join(",")}}`)
    .limit(limit);
  return { rows: (data ?? []) as SimilarInput[], error: error?.message ?? null };
}
