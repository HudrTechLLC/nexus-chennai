import "server-only";
import { publicClient } from "@/lib/publicApi";
import type { AppealImage } from "@/lib/appealImages";
import { isPublicId, type CrimeCard, type HexCrimes } from "@/lib/publicCards";
import { PUBLIC_CRIME_ID_RE } from "@/lib/tip";
import type { CrimeCardFields } from "@/lib/tipPrefill";

/** A published appeal as the public sees it (spec D3.13; 0004_03 public_appeals). */
export type Appeal = {
  id: string; title: string; category: string; area: string; cell: string; week: string; time_window: string;
  summary: string; looking_for: string[]; images: AppealImage[]; tip_count: number; published_at: string | null;
};

/** area: the card panel's label for the hex, only on cells that have cards (0007_13). */
export type PublicCell = { cell: string; n: number; by_category: Record<string, number>; appeal: boolean; area?: string | null };
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

/**
 * One public crime card for the /tip/new ?about= prefill (0007_11 public_crime). Null for a malformed or
 * unknown id, a crime that is not public, or any error (the form then simply starts empty).
 */
export async function getCrimeCard(publicId: string): Promise<CrimeCardFields | null> {
  if (!PUBLIC_CRIME_ID_RE.test(publicId)) return null;
  try {
    const { data, error } = await publicClient().rpc("public_crime", { p_public_id: publicId });
    return error ? null : ((data as CrimeCardFields | null) ?? null);
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

/** Cards for one hex (0007_11 public_hex_crimes): safe fields only; empty under the >=3 rule. */
export async function getHexCrimes(cell: string, days: number, type: string | null): Promise<{ hex: HexCrimes | null; error: string | null }> {
  try {
    const { data, error } = await publicClient().rpc("public_hex_crimes", { p_cell: cell, p_days: days, p_category: type });
    return { hex: (data as HexCrimes) ?? null, error: error ? "Crimes for this area are unavailable right now." : null };
  } catch {
    return { hex: null, error: "Crimes for this area are unavailable right now." };
  }
}

/** One card by its public id (0007_11 public_crime), or null when it is unknown or no longer public. */
export async function getPublicCrime(publicId: string): Promise<CrimeCard | null> {
  if (!isPublicId(publicId)) return null;
  try {
    const { data } = await publicClient().rpc("public_crime", { p_public_id: publicId });
    return (data as CrimeCard | null) ?? null;
  } catch {
    return null;
  }
}
