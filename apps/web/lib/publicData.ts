import "server-only";
import { publicClient } from "@/lib/publicApi";
import type { AppealImage } from "@/lib/appealImages";

/** A published appeal as the public sees it (spec D3.13; 0004_03 public_appeals). */
export type Appeal = {
  id: string; title: string; category: string; area: string; cell: string; week: string; time_window: string;
  summary: string; looking_for: string[]; images: AppealImage[]; tip_count: number; published_at: string | null;
};

export type PublicCell = { cell: string; n: number; by_category: Record<string, number>; appeal: boolean };
export type PublicMap = { days: number; min_count: number; cells: PublicCell[] };

/** Server-side reads through the anon RPCs; the visitor's browser never contacts Supabase. */
export async function getAppeals(): Promise<{ appeals: Appeal[]; error: string | null }> {
  try {
    const { data, error } = await publicClient().rpc("public_appeals");
    return { appeals: (data as Appeal[]) ?? [], error: error ? "Appeals are unavailable right now." : null };
  } catch {
    return { appeals: [], error: "Appeals are unavailable right now." };
  }
}

export async function getAppeal(id: string): Promise<Appeal | null> {
  if (!/^[A-Za-z0-9-]{1,40}$/.test(id)) return null;
  try {
    const { data } = await publicClient().rpc("public_appeal", { p_id: id });
    return (data as Appeal | null) ?? null;
  } catch {
    return null;
  }
}

export async function getPublicMap(days: number): Promise<{ map: PublicMap | null; error: string | null }> {
  try {
    const { data, error } = await publicClient().rpc("public_map_cells", { p_days: days, p_min: 3 });
    return { map: (data as PublicMap) ?? null, error: error ? "The map is unavailable right now." : null };
  } catch {
    return { map: null, error: "The map is unavailable right now." };
  }
}
