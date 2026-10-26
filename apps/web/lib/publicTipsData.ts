import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { linkPublicTips, PUBLIC_TIPS_CAP, type PublicTipRow, type PublicTipsFeed } from "@/lib/publicTips";

const TIP_COLUMNS = "tip_id, received_week, category, status, approx_cell, approx_cell_fine, public_incident_id, about_crime_id";

/**
 * Tips tied to `crimeIds` (WS3-28), read with the officer's session (RLS; never the service key).
 * Police can read every tip, so can_read_crime is applied here: tips are only looked up for the crimes the
 * viewer can read in full, which is exactly what `crimes` returns under its RLS (own station for station
 * officers, every crime for analysts and up, the same rule as can_read_crime in 0002).
 */
export async function fetchPublicTips(sb: SupabaseClient, crimeIds: string[]): Promise<PublicTipsFeed> {
  const ids = Array.from(new Set(crimeIds)).slice(0, 200);
  if (ids.length === 0) return { tips: [], quarantined: 0, unreadableCrimes: 0 };
  const { data: readable } = await sb.from("crimes").select("crime_id").in("crime_id", ids);
  const ok = (readable ?? []).map((r: { crime_id: string }) => r.crime_id);
  const unreadableCrimes = ids.length - ok.length;
  if (ok.length === 0) return { tips: [], quarantined: 0, unreadableCrimes };

  const [appeals, about, reviews] = await Promise.all([
    sb.from("public_incidents").select("public_incident_id, crime_id").in("crime_id", ok).limit(200),
    sb.from("tips").select(TIP_COLUMNS).in("about_crime_id", ok).limit(PUBLIC_TIPS_CAP * 2),
    sb.from("tip_reviews").select("tip_id, crime_id").in("crime_id", ok).limit(500),
  ]);
  const appealRows = (appeals.data ?? []) as { public_incident_id: string; crime_id: string | null }[];
  const reviewRows = (reviews.data ?? []) as { tip_id: string; crime_id: string | null }[];
  const appealIds = appealRows.map((a) => a.public_incident_id);
  const reviewTipIds = Array.from(new Set(reviewRows.map((r) => r.tip_id)));
  const [byAppeal, byReview] = await Promise.all([
    appealIds.length ? sb.from("tips").select(TIP_COLUMNS).in("public_incident_id", appealIds).limit(PUBLIC_TIPS_CAP * 2) : { data: [] },
    reviewTipIds.length ? sb.from("tips").select(TIP_COLUMNS).in("tip_id", reviewTipIds).limit(PUBLIC_TIPS_CAP * 2) : { data: [] },
  ]);
  const tips = [...(about.data ?? []), ...(byAppeal.data ?? []), ...(byReview.data ?? [])] as PublicTipRow[];
  return linkPublicTips({ crimeIds: ok, unreadableCrimes, appeals: appealRows, reviews: reviewRows, tips });
}
